import os, re, shutil, sqlite3
import json, html
from datetime import datetime, timezone

from flask import Flask, request, redirect, send_from_directory, Response
from flask_cors import CORS
import concurrent.futures
import langcodes
import threading
from io import StringIO
import logging
from logging.handlers import RotatingFileHandler

# import local modules
from providers import komga
from providers import aria2
from providers import ehentai
from providers import nhentai
from utils import check_dirs, is_valid_zip, parse_filename, TaskStatus, task_failure_notification, AppriseConfig
import cbztool
from database import task_db
from config import load_config, save_config

from providers.ehtranslator import EhTagTranslator

# 配置 Flask 以服务 Vue.js 静态文件
# 在生产环境中，Vue.js 应用会被构建到 `webui/dist` 目录
# Flask 将从这个目录提供静态文件
app = Flask(
    __name__,
    static_folder='../webui/dist', # Vue.js 构建后的完整目录（包含index.html和assets）
    static_url_path='/static-assets' # 将静态文件URL前缀改为/static-assets，避免与前端路由冲突
)
CORS(app) # 在 Flask 应用中启用 CORS
# 过滤掉 /api/task_stats 的访问日志
class StatsFilter(logging.Filter):
    def filter(self, record):
        return 'GET /api/task_stats' not in record.getMessage()

logging.getLogger('werkzeug').addFilter(StatsFilter())
# 设置5001端口为默认端口

# 创建一个线程池用于并发处理任务
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

tasks = {}
tasks_lock = threading.Lock()

class TaskInfo:
    def __init__(self, future, logger, log_buffer):
        self.future = future
        self.logger = logger
        self.log_buffer = log_buffer
        self.status = TaskStatus.IN_PROGRESS  # "完成"、"取消"、"错误"
        self.error = None
        self.filename = None # 初始 filename 为 None
        self.progress = 0  # 进度百分比 0-100
        self.downloaded = 0  # 已下载字节数
        self.total_size = 0  # 总字节数
        self.speed = 0  # 下载速度 B/s
        self.cancelled = False  # 取消标志

class SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'

# 日志初始化
LOG_FILE = "./data/app.log"

def json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        mimetype="application/json"
    )

def init_global_logger():
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(LOG_FILE, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

global_logger = init_global_logger()

def get_task_logger(task_id):
    log_buffer = StringIO()
    logger = logging.getLogger(f"task_{task_id}")
    logger.setLevel(logging.INFO)

    # 清除旧的 handlers，以防重试任务时重复添加
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(f'%(asctime)s [%(levelname)s] [task:{task_id}] %(message)s')

    # Handler 1: 写入内存缓冲区 (用于 API)
    buffer_handler = logging.StreamHandler(log_buffer)
    buffer_handler.setFormatter(formatter)
    logger.addHandler(buffer_handler)

    # Handler 2: 写入终端 (用于 Docker logs)
    console_handler = logging.StreamHandler()  # 默认输出到 sys.stderr
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 阻止日志向上传播到 root logger，避免 werkzeug 环境下重复输出
    logger.propagate = False

    return logger, log_buffer


def check_config():
    TRUE_VALUES = {'true', 'enable', '1', 'yes', 'on'}
    config_data = load_config()
    
    # 通用设置
    general = config_data.get('general', {})
    app.config['port'] = int(general.get('port', 5001))
    app.config['download_torrent'] = str(general.get('download_torrent', 'false')).lower() in TRUE_VALUES
    app.config['keep_torrents'] = str(general.get('keep_torrents', 'false')).lower() in TRUE_VALUES
    app.config['keep_original_file'] = str(general.get('keep_original_file', 'false')).lower() in TRUE_VALUES
    app.config['prefer_japanese_title'] = str(general.get('prefer_japanese_title', 'true')).lower() in TRUE_VALUES
    app.config['move_path'] = str(general.get('move_path', '')).rstrip('/') or None
    
    advanced = config_data.get('advanced', {})
    app.config['tags_translation'] = str(advanced.get('tags_translation', 'false')).lower() in TRUE_VALUES
    app.config['remove_ads'] = str(advanced.get('remove_ads', 'false')).lower() in TRUE_VALUES
    app.config['ehentai_genre'] = str(advanced.get('ehentai_genre', 'false')).lower() in TRUE_VALUES
    app.config['aggressive_series_detection'] = str(advanced.get('aggressive_series_detection', 'false')).lower() in TRUE_VALUES
    app.config['apprise'] = str(advanced.get('apprise', '')).strip() or None
    if app.config['apprise']: global_logger.info("通知服务已启用")

    # E-Hentai 设置
    ehentai_config = config_data.get('ehentai', {})
    cookie = ehentai_config.get('cookie', '')
    app.config['eh_cookie'] = {"cookie": cookie} if cookie else {"cookie": ""}

    # nhentai 设置
    nhentai_config = config_data.get('nhentai', {})
    nhentai_cookie = nhentai_config.get('cookie', '')
    app.config['nhentai_cookie'] = {"cookie": nhentai_cookie} if nhentai_cookie else {"cookie": ""}

    eh = ehentai.EHentaiTools(cookie=app.config['eh_cookie'], logger=global_logger)
    nh = nhentai.NHentaiTools(cookie=app.config['nhentai_cookie'], logger=global_logger)
    hath_toggle = eh.is_valid_cookie()
    nh_toggle = nh.is_valid_cookie()

    # Aria2 RPC 设置
    aria2_config = config_data.get('aria2', {})
    aria2_enable = str(aria2_config.get('enable', 'false')).lower() in TRUE_VALUES

    if aria2_enable:
        global_logger.info("开始测试 Aria2 RPC 的连接")
        app.config['aria2_server'] = str(aria2_config.get('server', '')).rstrip('/')
        app.config['aria2_token'] = str(aria2_config.get('token', ''))
        app.config['aria2_download_dir'] = str(aria2_config.get('download_dir', '')).rstrip('/') or None
        app.config['real_download_dir'] = str(aria2_config.get('mapped_dir', '')).rstrip('/') or app.config['aria2_download_dir']

        rpc = aria2.Aria2RPC(url=app.config['aria2_server'], token=app.config['aria2_token'], logger=global_logger)
        try:
            result = rpc.get_global_stat()
            if 'result' in result:
                global_logger.info("Aria2 RPC 连接正常")
                aria2_toggle = True
            else:
                global_logger.error("Aria2 RPC 连接异常, 种子下载功能将不可用")
                aria2_toggle = False
        except Exception as e:
            global_logger.error(f"Aria2 RPC 连接异常: {e}")
            aria2_toggle = False
    else:
        global_logger.info("Aria2 RPC 功能未启用")
        aria2_toggle = False

    # Komga API 设置
    komga_config = config_data.get('komga', {})
    komga_enable = str(komga_config.get('enable', 'false')).lower() in TRUE_VALUES
    app.config['komga_oneshot'] = str(komga_config.get('oneshot', '_oneshot'))

    if komga_enable:
        global_logger.info("开始测试 Komga API 的连接")
        app.config['komga_server'] = str(komga_config.get('server', '')).rstrip('/')
        app.config['komga_token'] = str(komga_config.get('token', ''))
        app.config['komga_library_id'] = str(komga_config.get('library_id', ''))

        kmg = komga.KomgaAPI(server=app.config['komga_server'], token=app.config['komga_token'], logger=global_logger)
        try:
            library = kmg.get_libraries(library_id=app.config['komga_library_id'])
            if library.status_code == 200:
                global_logger.info("Komga API 连接成功")
                komga_toggle = True
            else:
                komga_toggle = False
                global_logger.error("Komga API 连接异常, 相关功能将不可用")
        except Exception as e:
            global_logger.error(f"Komga API 连接异常: {e}")
            komga_toggle = False
    else:
        global_logger.info("Komga API 功能未启用")
        komga_toggle = False

    app.config['hath_toggle'] = hath_toggle
    app.config['nh_toggle'] = nh_toggle
    app.config['aria2_toggle'] = aria2_toggle
    app.config['komga_toggle'] = komga_toggle
    app.config['checking_config'] = False
    global eh_translator
    eh_translator = EhTagTranslator(enable_translation=app.config.get('tags_translation', True))

def get_eh_mode(config, mode):
    aria2 = config.get('aria2_toggle', False)
    hath = config.get('hath_toggle', False)
    download_torrent = mode in ("torrent", "1") if mode else config.get('download_torrent', True)
    if hath and not aria2:
        return "archive"
    if aria2 and download_torrent:
        if hath:
            return "both"
        else:
            return "torrent"
    elif hath:
        return "archive"
    return "both"

def send_to_aria2(url=None, torrent=None, dir=None, out=None, logger=None, task_id=None):
    # 检查任务是否被取消
    if task_id:
        check_task_cancelled(task_id)

    rpc = aria2.Aria2RPC(app.config['aria2_server'], app.config['aria2_token'])
    if url != None:
        result = rpc.add_uri(url, dir=dir, out=out)
        if logger: logger.info(result)
    elif torrent != None:
        result = rpc.add_torrent(torrent, dir=dir, out=out)
        if not app.config['keep_torrents'] == True:
            os.remove(torrent)
        if logger: logger.info(result)
    gid = result['result']

    # 检查任务是否被取消
    if task_id:
        check_task_cancelled(task_id)

    # 监视 aria2 的下载进度
    file = rpc.listen_status(gid, logger=logger, task_id=task_id, tasks=tasks, tasks_lock=tasks_lock)
    if file == None:
        if logger: logger.info("疑似为死种, 尝试用 Arichive 的方式下载")
        return None
    else:
        filename = os.path.basename(file)
        if filename.lower().endswith(('.zip', '.cbz')):
            local_file_path = os.path.join(app.config['real_download_dir'], filename)
        else:
            local_file_path = os.path.join(app.config['real_download_dir'], os.path.basename(os.path.dirname(file)))

    # 完成下载后, 为压缩包添加元数据
    if os.path.exists(file):
        print(f"下载完成: {local_file_path}")
        if logger: logger.info(f"下载完成: {local_file_path}")
    return local_file_path

def sanitize_filename(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', s)

def normalize_tilde(filename: str) -> str:
    filename = re.sub(r'([话話])(?!\s)', r'\1 ', filename)
    filename = re.sub(r'([~⁓～—_「-])', ' ', filename)
    return filename

def clean_name(title):
    name = re.sub(r'[\s\-—_:：•·․,，。\'’?？!！~⁓～]+$', '', title)
    return name.strip()

def extract_before_chapter(filename):
    patterns = [
        # 1 中文/阿拉伯数字
        r'(.*?)第?\s*[一二三四五六七八九十\d]+\s*[卷巻话話回迴編篇章册冊席期辑輯节節部]',
        # 2. 数字在前，关键字在后
        r'(.*?)\d+\s*[卷巻话話回迴編篇章册冊席期辑輯节節部]',
        # 3. 关键字在前，数字在后
        r'(.*?)[卷巻回迴編篇章册冊席期辑輯节節部]\s*[一二三四五六七八九十\d]+',
        # 4. Vol/Vol./vol/v/V + 数字
        r'(.*?)\s*(?:vol|v|#|＃)[\s\.]*\d+',
        # 5. 圆方括号+数字
        r'(.*?)\s*[\[\(（]\d+[\]\)）]\s*$',
        # 6. 上中下前后
        r'^(.*?)(?:[上中下前后後](?:編|回)|[上中下前后後]\s*$)',
        # 7. 纯数字
        r'(.*?)\s*\d+(\s|$)',
    ]

    filename = normalize_tilde(filename)
    for pat in patterns:
        m = re.search(pat, filename, re.I)
        if m:
            return clean_name(m.group(1)).strip()
    
    # 如果没有匹配任何章节模式 → 返回第一个空格前的内容
    is_aggressive_series_detection = app.config.get('aggressive_series_detection', False)
    if is_aggressive_series_detection:
        filename = filename.strip()
        idx = filename.find(' ')
        if idx == -1:
            return  clean_name(filename).strip()
        return clean_name(filename[:idx]).strip()

def fill_field(comicinfo, field, tags, prefixes):
    for prefix in prefixes:
        values = []
        for t in tags:
            if t.startswith(f"{prefix}:"):
                name = t[len(prefix)+1:]
                name = eh_translator.get_translation(name, prefix)
                values.append(name)
        if values:
            comicinfo[field] = ", ".join(values)
            return

def add_tag_to_front(comicinfo, new_tag: str):
    new_tag = new_tag.strip().lower()
    if not new_tag:
        return
    if 'Tags' in comicinfo and comicinfo['Tags']:
        tags = [t.strip() for t in comicinfo['Tags'].split(',') if t.strip()]
        if new_tag not in tags:
            tags.insert(0, new_tag)
        comicinfo['Tags'] = ', '.join(tags)
    else:
        comicinfo['Tags'] = new_tag

def parse_eh_tags(tags):
    comicinfo = {'AgeRating':'R18+'}
    #char_list = []
    tag_list = []
    collectionlist = []
    for tag in tags:
        # 因为 komga 这样软件并不支持 EH Tag 的 namespace，照搬会显得很别扭，所以这里会像 nhentai 那样，将一些 tag 的 namespace 去除
        matchTag = re.match(r'(.+?):(.*)',tag)
        if matchTag:
            namespace = matchTag.group(1).lower()
            tag_name = matchTag.group(2).lower()
            if namespace == 'language':
                if tag_name not in ['translated', 'rewrite']:
                    language_code = langcodes.find(tag_name).language
                    if language_code:
                        comicinfo['LanguageISO'] = language_code # 转换为BCP-47
            elif namespace == 'parody':
                # 提取 parody 内容至 SeriesGroup
                if tag_name not in ['original', 'various']:
                    #kanji_parody = ehentai.get_original_tag(tag_name) # 将提取到合集的 Tag 翻译为日文
                    tag_name = eh_translator.get_translation(tag_name, namespace)
                    tag_list.append(f"{namespace}:{tag_name}") #  此处保留 namespace，方便所有 parody 相关的 tag 能排序在一块
                    #if not kanji_parody == None and not app.config.get('tags_translation', True):
                    #    comicinfo['Genre'] = comicinfo['Genre'] + ', Parody'
                    #    collectionlist.append(kanji_parody)
                    #else:
                    #    collectionlist.append(tag_name)
            elif namespace in ['character']:
                tag_name = eh_translator.get_translation(tag_name, namespace)
                tag_list.append(f"{namespace}:{tag_name}") # 保留 namespace，理由同 parody
            elif namespace == 'female' or namespace == 'mixed':
                tag_name = eh_translator.get_translation(tag_name, namespace)
                tag_list.append(tag_name) # 去掉 namespace, 仅保留内容
            elif namespace == 'male': # male 与 female 存在相同的标签, 但它们在作品中表达的含义是不同的, 为了减少歧义，这里将会丢弃所有 male 相关的共同标签，但是保留 male 限定的标签
                if tag_name in ehentai.male_only_taglist():
                    tag_name = eh_translator.get_translation(tag_name, namespace)
                    tag_list.append(tag_name)
            elif namespace == 'other' or namespace == 'tag':
                if tag_name not in ['extraneous ads',  'already uploaded', 'missing cover', 'forbidden content', 'replaced', 'compilation', 'incomplete', 'caption']:
                    if namespace == 'tag':
                        tag_name = eh_translator.get_translation(tag_name)
                    else:
                        tag_name = eh_translator.get_translation(tag_name, namespace)
                    tag_list.append(tag_name)
    # 进行以下去重
    tag_list_sorted = sorted(set(tag_list), key=tag_list.index)
    # 为 webtoon 以外的漫画指定翻页顺序
    if not 'webtoon' in tag_list_sorted:
        comicinfo['Manga'] = 'YesAndRightToLeft'
    comicinfo['Tags'] = ', '.join(tag_list_sorted)
    if not collectionlist == []: comicinfo['SeriesGroup'] = ', '.join(collectionlist)
    return comicinfo

# 解析来自 E-Hentai 或 nhentai API 的画廊信息
def parse_gmetadata(data):
    comicinfo = {}
    # 检查是否为 nhentai 数据（没有 token 字段）
    if 'token' not in data or data.get('token') == '':
        # nhentai 数据
        if 'gid' in data:
            comicinfo['Web'] = f"https://nhentai.net/g/{data['gid']}/"
    else:
        # ehentai 数据
        comicinfo['Web'] = (
            f"https://exhentai.org/g/{data['gid']}/{data['token']}/, "
            f"https://e-hentai.org/g/{data['gid']}/{data['token']}/"
        )
    if 'tags' in data:
        comicinfo.update(parse_eh_tags(data['tags']))
    # 根据 ehentai_genre 设置决定是否将 Categories 作为 Genre 还是作为 Tag 使用
    if not data['category'].lower() == 'non-h':
        comicinfo['Genre'] = 'Hentai'
    if data['category'].lower() not in ['manga', 'misc', 'asianporn', 'private']:
        category = eh_translator.get_translation(data['category'], 'reclass')
        if app.config['ehentai_genre']:
            if 'Genre' in comicinfo:
                comicinfo['Genre'] = comicinfo['Genre'] + ', ' + category
            else:
                comicinfo['Genre'] = category
        else:
            # 将 Categories 作为 Tags 至于最前方
            add_tag_to_front(comicinfo, category)
    # 从标题中提取作者信息
    if app.config['prefer_japanese_title'] and not data['title_jpn'] == "":
        text = html.unescape(data['title_jpn'])
    else:
        text = html.unescape(data['title'])
    comic_market = re.search(r'\(C(\d+)\)', text)
    if comic_market:
       add_tag_to_front(comicinfo, f"c{comic_market.group(1)}")
    if data['category'].lower() not in ['imageset']:
        comicinfo['Title'], comicinfo['Writer'], comicinfo['Penciller'] = parse_filename(text, eh_translator)
    else:
        comicinfo['Title'] = text

    if comicinfo['Writer'] == None:
        tags = data.get("tags", [])
        fill_field(comicinfo, "Writer", tags, ["group", "artist"])
    if comicinfo['Penciller'] == None:
        tags = data.get("tags", [])
        fill_field(comicinfo, "Penciller", tags, ["artist", "group"])
    # 当 tags 中存在 multi-work series 时, 尝试为 AlternateSeries 字段赋值
    series_keywords = ["multi-work series", "系列作品"]
    if comicinfo and comicinfo.get('Tags'):
        tags_list = [tag.strip() for tag in comicinfo['Tags'].split(', ')]
        matched = any(k.lower() == t.lower() for k in series_keywords for t in tags_list)
        if matched:
            if comicinfo and comicinfo.get('Title'):
                comicinfo['AlternateSeries'] = extract_before_chapter(comicinfo['Title'])
    return comicinfo

def check_task_cancelled(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
        if task and task.cancelled:
            raise Exception("Task was cancelled by user")

def download_task(url, mode, task_id, logger=None):
    if logger: logger.info(f"Task {task_id} started, downloading from: {url}")

    # 检查是否被取消
    check_task_cancelled(task_id)

    # 检测 URL 类型并选择相应的下载器
    result = download_gallery_task(url, mode, task_id, logger=logger)
    
    # 任务完成通知仍然在此处处理
    if app.config['apprise'] and result and result.get('Title'):
        msg = AppriseConfig(app.config['apprise'])
        msg_content = [
            result['Title'],
            f"TaskID: {task_id}",
            f"作者: {result.get('Writer', '未知')}",
            f"画师: {result.get('Penciller', '未知')}"
        ]
        if result.get('AlternateSeries'):
            msg_content.append(result['AlternateSeries'])
        msg.send_message(message=("\n").join(msg_content), title="Hentai Assistant 任务完成")

def post_download_processing(dl, metadata, task_id, logger=None, is_nhentai=False):
    try:
        # 检查是否被取消
        check_task_cancelled(task_id)

        if not dl:
            return None

        # 创建 ComicInfo.xml 并转换为 CBZ
        if metadata.get('Writer') or metadata.get('Tags'):
            author = metadata.get('Penciller') or metadata.get('Writer') or 'Other'
            writer = metadata.get('Writer') or metadata.get('Penciller') or 'Other'
            series = metadata.get('AlternateSeries') or app.config['komga_oneshot']
            move_path = app.config.get('move_path') or os.path.dirname(dl)
            move_file_path = move_path.format(**SafeDict({
                'author': author,
                'penciller': author,
                'writer': writer,
                'series': series,
                'filename': os.path.basename(dl)
                })
            )
            if not os.path.basename(move_file_path).lower().endswith(('.zip', '.cbz')):
                move_file_path = os.path.join(move_file_path, os.path.basename(dl))
            cbz = cbztool.write_xml_to_zip(dl, metadata, app=app, logger=logger)
            if cbz and is_valid_zip(cbz):
                # 移动到指定目录（komga/lanraragi，可选）
                move_file_path = os.path.splitext(move_file_path)[0] + '.cbz'
                os.makedirs(os.path.dirname(move_file_path), exist_ok=True)
                shutil.move(cbz, move_file_path)
                (logger.info if logger else print)(f"文件移动到指定目录: {move_file_path}")
                dl = move_file_path
            else:
                return None

        # 检查是否被取消
        check_task_cancelled(task_id)

        # 触发 Komga 媒体库入库扫描
        if app.config['komga_toggle'] and is_valid_zip(dl):
            if app.config['komga_library_id']:
                kmg = komga.KomgaAPI(server=app.config['komga_server'], token=app.config['komga_token'], logger=logger)
                if app.config['komga_library_id']:
                    kmg.scan_library(app.config['komga_library_id'])

        return dl

    except Exception as e:
        if logger: logger.error(f"Post-download processing failed: {e}")
        raise e

def download_gallery_task(url, mode, task_id, logger=None):
    # 检查是否被取消
    check_task_cancelled(task_id)

    # 判断平台
    is_nhentai = 'nhentai.net' in url

    if is_nhentai:
        gallery_tool = nhentai.NHentaiTools(cookie=app.config.get('nhentai_cookie'), logger=logger)
    else:
        gallery_tool = ehentai.EHentaiTools(cookie=app.config.get('eh_cookie'), logger=logger)

    # 获取画廊元数据
    gmetadata = gallery_tool.get_gmetadata(url)
    if not gmetadata or 'gid' not in gmetadata:
        raise ValueError("Failed to retrieve valid gmetadata for the given URL.")
    # 获取标题
    if 'title_jpn' in gmetadata and gmetadata['title_jpn'] != None:
        title = html.unescape(gmetadata['title_jpn'])
    else:
        title = html.unescape(gmetadata['title'])
    filename = f"{sanitize_filename(title)} [{gmetadata['gid']}]"
    if not is_nhentai:
        filename += ".zip"

    if logger: logger.info(f"准备下载: {filename}")

    # 更新内存和数据库任务信息
    with tasks_lock:
        if task_id in tasks:
            tasks[task_id].filename = title
    task_db.update_task(task_id, filename=filename)

    check_task_cancelled(task_id)

    # 下载路径
    download_dir = './data/download/nhentai' if is_nhentai else './data/download/ehentai'
    path = os.path.join(os.path.abspath(check_dirs(download_dir)), filename)

    dl = None
    if is_nhentai:
        # nhentai 直接下载
        dl = gallery_tool.download_gallery(url, path, task_id, tasks, tasks_lock)
    else:
        # ehentai 下载模式选择
        eh_mode = get_eh_mode(app.config, mode)
        result = gallery_tool.archive_download(url=url, mode=eh_mode)

        check_task_cancelled(task_id)

        if result:
            if result[0] == 'torrent':
                dl = send_to_aria2(torrent=result[1], dir=app.config['aria2_download_dir'], out=filename, logger=logger, task_id=task_id)
                if dl is None:
                    # 死种尝试 archive
                    result = gallery_tool.archive_download(url=url, mode='archive')
            elif result[0] == 'archive':
                if not app.config['aria2_toggle']:
                    dl = gallery_tool._download(
                        url=result[1],
                        path=path,
                        task_id=task_id,
                        tasks=tasks,
                        tasks_lock=tasks_lock
                    )
                else:
                    dl = send_to_aria2(url=result[1], dir=app.config['aria2_download_dir'], out=filename, logger=logger, task_id=task_id)

    check_task_cancelled(task_id)
    
    
    metadata = parse_gmetadata(gmetadata)
    # 统一后处理
    final_path = post_download_processing(dl, metadata, task_id, logger, is_nhentai=is_nhentai)

    if final_path and is_valid_zip(final_path):
        if logger: logger.info(f"Task {task_id} completed successfully.")
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id].status = TaskStatus.COMPLETED
        task_db.update_task(task_id, status=TaskStatus.COMPLETED)
        return metadata # 返回 metadata 以便装饰器或调用者处理完成通知
    else:
        error_message = "Downloaded file is not a valid zip archive."
        # 此处直接抛出异常，装饰器会捕获并发送失败通知
        raise ValueError(error_message)

@app.route('/api/download', methods=['GET'])
def download_url():
    url = request.args.get('url')
    mode = request.args.get('mode')
    if not url:
        return json_response({'error': 'No URL provided'}), 400
    # 两位年份+月日时分秒，使用UTC时间避免时区问题
    task_id = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S%f')
    logger, log_buffer = get_task_logger(task_id)
    
    # 动态应用装饰器
    decorated_download_task = task_failure_notification(task_id, logger, tasks_lock, tasks, app.config)(download_task)
    
    future = executor.submit(decorated_download_task, url, mode, task_id, logger)
    with tasks_lock:
        tasks[task_id] = TaskInfo(future, logger, log_buffer)

    # 添加任务到数据库，包含URL和mode信息用于重试
    task_db.add_task(task_id, status=TaskStatus.IN_PROGRESS, url=url, mode=mode)

    return json_response({'message': f"Download task for {url} started with task ID {task_id}.", 'task_id': task_id}), 202

@app.route('/api/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return json_response({'error': 'Task not found'}), 404

    # 设置取消标志
    task.cancelled = True

    cancelled = task.future.cancel()
    if cancelled:
        with tasks_lock:
            task.status = TaskStatus.CANCELLED
        # 更新数据库状态
        task_db.update_task(task_id, status=TaskStatus.CANCELLED)
        return json_response({'message': 'Task cancelled'})
    else:
        return json_response({'message': 'Task could not be cancelled (可能已在运行或已完成)'})

@app.route('/api/retry_task/<task_id>', methods=['POST'])
def retry_task(task_id):
    # 从数据库获取任务信息
    task_info = task_db.get_task(task_id)
    if not task_info:
        return json_response({'error': 'Task not found'}), 404

    # 检查任务状态是否为失败
    if task_info['status'] != TaskStatus.ERROR:
        return json_response({'error': 'Only failed tasks can be retried'}), 400

    # 检查是否有URL信息
    if not task_info.get('url'):
        return json_response({'error': 'Task URL information is missing, cannot retry'}), 400

    # 获取URL和mode
    url = task_info['url']
    mode = task_info.get('mode')

    # 创建新的任务ID
    new_task_id = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S%f')

    # 添加新任务到数据库
    task_db.add_task(new_task_id, status=TaskStatus.IN_PROGRESS, url=url, mode=mode)

    # 删除原来的失败任务
    try:
        with sqlite3.connect('./data/tasks.db') as conn:
            conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
            conn.commit()
        print(f"已从数据库删除失败任务 {task_id}")
    except sqlite3.Error as e:
        print(f"删除失败任务时发生数据库错误: {e}")

    # 从内存中删除原来的失败任务
    with tasks_lock:
        if task_id in tasks:
            # 关闭日志缓冲区
            if hasattr(tasks[task_id], 'log_buffer'):
                tasks[task_id].log_buffer.close()
            del tasks[task_id]

    # 创建新的任务执行
    logger, log_buffer = get_task_logger(new_task_id)
    future = executor.submit(download_task, url, mode, new_task_id, logger)

    # 更新内存中的任务信息
    with tasks_lock:
        tasks[new_task_id] = TaskInfo(future, logger, log_buffer)

    return json_response({'message': f'Task retry started with new ID {new_task_id}', 'task_id': new_task_id}), 202


@app.route('/api/task_log/<task_id>')
def get_task_log(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return json_response({'error': 'Task not found'}), 404
    log_content = task.log_buffer.getvalue()
    return json_response({'log': log_content})

@app.route('/api/task/<task_id>')
def get_task(task_id):
    # 首先检查内存中的任务
    with tasks_lock:
        memory_task = tasks.get(task_id)
        if memory_task:
            task_data = {
                'id': task_id,
                'status': memory_task.status,
                'error': memory_task.error,
                'filename': memory_task.filename,
                'progress': memory_task.progress,
                'downloaded': memory_task.downloaded,
                'total_size': memory_task.total_size,
                'speed': memory_task.speed,
                'log': memory_task.log_buffer.getvalue()
            }
            return json_response(task_data)

    # 如果内存中没有，检查数据库
    db_task = task_db.get_task(task_id)
    if db_task:
        return json_response(db_task)

    return json_response({'error': 'Task not found'}), 404

@app.route('/api/config', methods=['GET'])
def get_config():
    config_data = load_config()

    # 添加状态信息
    config_data['status'] = {
        'hath_toggle': bool(app.config.get('hath_toggle', False)),
        'nh_toggle': bool(app.config.get('nh_toggle', False)),
        'aria2_toggle': bool(app.config.get('aria2_toggle', False)),
        'komga_toggle': bool(app.config.get('komga_toggle', False)),
    }
    return json_response(config_data)

@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.get_json()
    if not data:
        return json_response({'error': 'Invalid JSON data'}), 400

    try:
        save_config(data)
    except Exception as e:
        return json_response({'error': f'Failed to save config: {e}'}), 500

    app.config['checking_config'] = True
    executor.submit(check_config)
    return json_response({'message': 'Config updated successfully', 'status_check_started': True}), 200

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    status_filter = request.args.get('status')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))

    # 从数据库获取任务列表
    db_tasks, total = task_db.get_tasks(status_filter, page, page_size)

    # 合并内存中的活跃任务信息
    with tasks_lock:
        for db_task in db_tasks:
            task_id = db_task['id']
            if task_id in tasks:
                memory_task = tasks[task_id]
                # 用内存中的最新信息更新数据库任务
                db_task.update({
                    'status': memory_task.status,
                    'error': memory_task.error,
                    'log': memory_task.log_buffer.getvalue(),
                    'filename': memory_task.filename,
                    'progress': memory_task.progress,
                    'downloaded': memory_task.downloaded,
                    'total_size': memory_task.total_size,
                    'speed': memory_task.speed
                })

                # 同步更新数据库
                task_db.update_task(
                    task_id,
                    status=memory_task.status,
                    error=memory_task.error,
                    log=memory_task.log_buffer.getvalue(),
                    filename=memory_task.filename,
                    progress=memory_task.progress,
                    downloaded=memory_task.downloaded,
                    total_size=memory_task.total_size,
                    speed=memory_task.speed
                )

    # 按任务ID降序排序（任务ID基于时间，新的ID更大）
    db_tasks.sort(key=lambda x: x.get('id', ''), reverse=True)

    # 获取各个状态的任务数量统计
    try:
        with sqlite3.connect('./data/tasks.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT
                    status,
                    COUNT(*) as count
                FROM tasks
                GROUP BY status
            ''')
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            # 获取各个状态的总数
            all_count = sum(status_counts.values())
            in_progress_count = status_counts.get(TaskStatus.IN_PROGRESS, 0)
            completed_count = status_counts.get(TaskStatus.COMPLETED, 0)
            cancelled_count = status_counts.get(TaskStatus.CANCELLED, 0)
            failed_count = status_counts.get(TaskStatus.ERROR, 0)
    except sqlite3.Error as e:
        print(f"Database error getting status counts: {e}")
        all_count = total
        in_progress_count = 0
        completed_count = 0
        failed_count = 0

    return json_response({
        'tasks': db_tasks,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
        'status_counts': {
            'all': all_count,
            'in-progress': in_progress_count,
            'completed': completed_count,
            'cancelled': cancelled_count,
            'failed': failed_count
        }
    })

@app.route('/api/task_stats', methods=['GET'])
def get_task_stats():
    """获取任务统计信息"""
    try:
        with sqlite3.connect('./data/tasks.db') as conn:
            conn.row_factory = sqlite3.Row
            # 获取各种状态的任务数量
            cursor = conn.execute('''
                SELECT
                    status,
                    COUNT(*) as count
                FROM tasks
                GROUP BY status
            ''')
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            # 获取总任务数
            cursor = conn.execute('SELECT COUNT(*) as total FROM tasks')
            total_tasks = cursor.fetchone()['total']

            # 获取进行中任务数
            in_progress = status_counts.get(TaskStatus.IN_PROGRESS, 0)

            # 获取已完成任务数
            completed = status_counts.get(TaskStatus.COMPLETED, 0)

            # 获取取消任务数
            cancelled = status_counts.get(TaskStatus.CANCELLED, 0)

            # 获取失败任务数（只包括错误）
            failed = status_counts.get(TaskStatus.ERROR, 0)

            return json_response({
                'total': total_tasks,
                'in_progress': in_progress,
                'completed': completed,
                'cancelled': cancelled,
                'failed': failed,
                'status_counts': status_counts
            })

    except sqlite3.Error as e:
        print(f"Database error getting task stats: {e}")
        return json_response({'error': 'Failed to get task statistics'}), 500

@app.route('/api/clear_tasks', methods=['POST'])
def clear_tasks():
    status_to_clear = request.args.get('status')
    if not status_to_clear:
        return json_response({'error': 'No status provided to clear'}), 400

    # 从数据库清除任务
    success = task_db.clear_tasks(status_to_clear)
    if not success:
        return json_response({'error': 'Failed to clear tasks from database'}), 500

    # 同时从内存清除对应任务
    with tasks_lock:
        tasks_to_keep = {}
        for tid, task_info in tasks.items():
            should_clear = False
            
            if status_to_clear == "all_except_in_progress":
                # 清除除了进行中任务外的所有任务
                should_clear = task_info.status != TaskStatus.IN_PROGRESS
            elif status_to_clear == "failed":
                # 清除失败状态的任务（对应数据库中的"错误"状态）
                should_clear = task_info.status == TaskStatus.ERROR
            elif status_to_clear == "completed":
                # 清除已完成的任务
                should_clear = task_info.status == TaskStatus.COMPLETED
            elif status_to_clear == "cancelled":
                # 清除取消的任务
                should_clear = task_info.status == TaskStatus.CANCELLED
            elif status_to_clear == "in-progress":
                # 清除进行中的任务
                should_clear = task_info.status == TaskStatus.IN_PROGRESS
            else:
                # 直接状态匹配
                should_clear = task_info.status == status_to_clear
            
            if should_clear:
                # 清除日志缓冲区
                if hasattr(task_info, 'log_buffer'):
                    task_info.log_buffer.close()
            else:
                tasks_to_keep[tid] = task_info
                
        tasks.clear()
        tasks.update(tasks_to_keep)

    return json_response({'message': f'Tasks with status "{status_to_clear}" cleared successfully'}), 200

# Catch-all 路由，用于服务 Vue.js 的 index.html
# 确保这个路由在所有 API 路由之后定义
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_vue_app(path):
    # 在开发模式下，我们不服务静态文件，而是让 Vue CLI 自己的服务器处理
    # 在生产模式下，我们服务构建后的 index.html
    if app.debug: # 如果是调试模式 (开发环境)
        return redirect(f"http://localhost:5173/{path}") # 重定向到 Vue 开发服务器
    else: # 如果是生产模式
        static_dir = app.static_folder
        # 首先尝试提供请求的路径作为静态文件（例如CSS/JS/图片等）
        requested_file = os.path.join(static_dir, path)
        if os.path.exists(requested_file) and not os.path.isdir(requested_file):
            return send_from_directory(static_dir, path)
        
        # 如果请求的不是静态文件，则提供 index.html 让 Vue Router 处理
        index_path = os.path.join(static_dir, 'index.html')
        if not os.path.exists(index_path):
            return "Vue.js application not built. Please run 'npm run build' in the webui directory.", 500
        return send_from_directory(static_dir, 'index.html')

if __name__ == '__main__':
    # 初始化时加载配置，config.py 会自动处理文件创建
    check_config()

    # 启动时迁移内存中的任务到数据库
    if tasks:
        global_logger.info("正在迁移内存中的任务到数据库...")
        success = task_db.migrate_memory_tasks(tasks)
        if success:
            global_logger.info("任务迁移完成")
        else:
            global_logger.error("任务迁移失败")

    # 将重启前的进行中任务标记为失败
    global_logger.info("正在检查并标记重启前的进行中任务...")
    try:
        with sqlite3.connect('./data/tasks.db') as conn:
            cursor = conn.execute('SELECT id FROM tasks WHERE status = ?', (TaskStatus.IN_PROGRESS,))
            in_progress_tasks = cursor.fetchall()
            if in_progress_tasks:
                for task_row in in_progress_tasks:
                    task_id = task_row[0]
                    conn.execute('UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?',
                               (TaskStatus.ERROR, '任务因应用重启而中断', datetime.now(timezone.utc).isoformat(), task_id))
                conn.commit()
                global_logger.info(f"已将 {len(in_progress_tasks)} 个进行中任务标记为失败")
            else:
                global_logger.info("没有发现进行中的任务")
    except sqlite3.Error as e:
        global_logger.error(f"标记进行中任务失败时发生数据库错误: {e}")

    try:
        # 在生产模式下，debug 应该设置为 False
        # 检查是否在Docker容器中运行
        is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER', False)
        debug_mode = not is_docker  # 在Docker中关闭debug模式
        app.run(host='0.0.0.0', port=app.config['port'], debug=debug_mode)
    finally:
        executor.shutdown()
