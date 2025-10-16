import os, re, shutil, sqlite3
import json, html
from datetime import datetime, timezone
import subprocess # 导入 subprocess 模块
import sys # 导入 sys 模块
import functools
import jinja2


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
from providers.ehtranslator import EhTagTranslator
from utils import check_dirs, is_valid_zip, TaskStatus
from notification import notify
import cbztool
from database import task_db
from config import load_config, save_config
from metadata_extractor import MetadataExtractor
from migrate import migrate_ini_to_yaml

# 全局变量用于存储子进程对象
notification_process = None
eh_translator = None
metadata_extractor = None

def start_notification_process():
    """启动 notification.py 子进程"""
    global notification_process
    if notification_process and notification_process.poll() is None:
        global_logger.info("notification.py 进程已在运行中。")
        return

    try:
        global_logger.info("正在启动 notification.py 子进程...")
        notification_process = subprocess.Popen([
            sys.executable,
            'src/notification.py'
        ])
        global_logger.info(f"notification.py 已作为子进程启动, PID: {notification_process.pid}")
    except Exception as e:
        global_logger.error(f"启动 notification.py 失败: {e}")

def stop_notification_process():
    """停止 notification.py 子进程"""
    global notification_process
    if notification_process and notification_process.poll() is None:
        global_logger.info(f"正在终止 notification.py 子进程, PID: {notification_process.pid}")
        notification_process.terminate()
        try:
            notification_process.wait(timeout=5)
            global_logger.info("notification.py 子进程已终止。")
        except subprocess.TimeoutExpired:
            global_logger.warning("notification.py 子进程在超时时间内未能终止，尝试强制终止。")
            notification_process.kill()
            notification_process.wait()
            global_logger.info("notification.py 子进程已强制终止。")
        finally:
            notification_process = None


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

def add_console_handler(logger, formatter):
    """Adds a console handler to the logger."""
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

def init_global_logger():
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        
        # Handler 1: 写入文件
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Handler 2: 写入终端
        add_console_handler(logger, formatter)
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
    add_console_handler(logger, formatter)

    # 阻止日志向上传播到 root logger，避免 werkzeug 环境下重复输出
    logger.propagate = False

    return logger, log_buffer

def update_eh_funds(eh_funds):
    """更新 eh_funds 到 app.config 和数据库"""
    if eh_funds is not None:
        # 始终将 eh_funds 构造成字典以提高可扩展性
        eh_funds_dict = {'GP': eh_funds}
        app.config['EH_FUNDS'] = eh_funds_dict
        task_db.set_global_state('eh_funds', json.dumps(eh_funds_dict))
        global_logger.info(f"E-Hentai GP 余额已更新: {eh_funds_dict['GP']}")

def check_config():
    """检查并加载应用配置，并根据配置变化管理通知子进程。"""
    global notification_process, eh_translator, metadata_extractor
    config_data = load_config()

    # 记录 Komga 的旧状态
    was_komga_enabled = app.config.get('KOMGA_TOGGLE', False)

    # 通用设置
    general = config_data.get('general', {})
    app.config['PORT'] = int(general.get('port', 5001))
    app.config['DOWNLOAD_TORRENT'] = general.get('download_torrent', False)
    app.config['KEEP_TORRENTS'] = general.get('keep_torrents', False)
    app.config['KEEP_ORIGINAL_FILE'] = general.get('keep_original_file', False)
    app.config['PREFER_JAPANESE_TITLE'] = general.get('prefer_japanese_title', True)
    app.config['MOVE_PATH'] = str(general.get('move_path', '')).rstrip('/') or None

    # 高级设置
    advanced = config_data.get('advanced', {})
    app.config['TAGS_TRANSLATION'] = advanced.get('tags_translation', False)
    app.config['REMOVE_ADS'] = advanced.get('remove_ads', False)
    app.config['AGGRESSIVE_SERIES_DETECTION'] = advanced.get('aggressive_series_detection', False)
    app.config['OPENAI_SERIES_DETECTION'] = advanced.get('openai_series_detection', False)

    # E-Hentai 设置
    ehentai_config = config_data.get('ehentai', {})
    cookie = ehentai_config.get('cookie', '')
    app.config['EH_COOKIE'] = {"cookie": cookie} if cookie else {"cookie": ""}

    # nhentai 设置
    nhentai_config = config_data.get('nhentai', {})
    nhentai_cookie = nhentai_config.get('cookie', '')
    app.config['NHENTAI_COOKIE'] = {"cookie": nhentai_cookie} if nhentai_cookie else {"cookie": ""}

    eh = ehentai.EHentaiTools(cookie=app.config['EH_COOKIE'], logger=global_logger)
    nh = nhentai.NHentaiTools(cookie=app.config['NHENTAI_COOKIE'], logger=global_logger)
    eh_valid, exh_valid, eh_funds = eh.is_valid_cookie()
    hath_toggle = (eh_valid, exh_valid)
    update_eh_funds(eh_funds)
    nh_toggle = nh.is_valid_cookie()

    # Aria2 RPC 设置
    aria2_config = config_data.get('aria2', {})
    aria2_enable = aria2_config.get('enable', False)

    if aria2_enable:
        global_logger.info("开始测试 Aria2 RPC 的连接")
        app.config['ARIA2_SERVER'] = str(aria2_config.get('server', '')).rstrip('/')
        app.config['ARIA2_TOKEN'] = str(aria2_config.get('token', ''))
        app.config['ARIA2_DOWNLOAD_DIR'] = str(aria2_config.get('download_dir', '')).rstrip('/') or None
        app.config['REAL_DOWNLOAD_DIR'] = str(aria2_config.get('mapped_dir', '')).rstrip('/') or app.config['ARIA2_DOWNLOAD_DIR']

        rpc = aria2.Aria2RPC(url=app.config['ARIA2_SERVER'], token=app.config['ARIA2_TOKEN'], logger=global_logger)
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
        app.config['ARIA2_SERVER'] = ''
        app.config['ARIA2_TOKEN'] = ''
        app.config['ARIA2_DOWNLOAD_DIR'] = None
        app.config['REAL_DOWNLOAD_DIR'] = None

    # Komga API 设置
    komga_config = config_data.get('komga', {})
    komga_enable = komga_config.get('enable', False)
    app.config['KOMGA_ONESHOT'] = str(komga_config.get('oneshot', '_oneshot'))

    if komga_enable:
        global_logger.info("开始测试 Komga API 的连接")
        app.config['KOMGA_SERVER'] = str(komga_config.get('server', '')).rstrip('/')
        app.config['KOMGA_USERNAME'] = str(komga_config.get('username', ''))
        app.config['KOMGA_PASSWORD'] = str(komga_config.get('password', ''))
        app.config['KOMGA_LIBRARY_ID'] = str(komga_config.get('library_id', ''))

        kmg = komga.KomgaAPI(server=app.config['KOMGA_SERVER'], username=app.config['KOMGA_USERNAME'], password=app.config['KOMGA_PASSWORD'],  logger=global_logger)
        try:
            library = kmg.get_libraries(library_id=app.config['KOMGA_LIBRARY_ID'])
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
        app.config['KOMGA_SERVER'] = ''
        app.config['KOMGA_USERNAME'] = ''
        app.config['KOMGA_PASSWORD'] = ''
        app.config['KOMGA_LIBRARY_ID'] = ''

    is_komga_enabled = komga_toggle

    # 只有在主工作进程中才管理子进程的生命周期，以避免 reloader 重复启动
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == 'true':
        is_config_update = app.config.get('CHECKING_CONFIG', False)

        if not is_komga_enabled:
            if was_komga_enabled:
                global_logger.info("Komga 功能已禁用，正在停止通知监听器...")
                stop_notification_process()
        else:
            if not was_komga_enabled:
                global_logger.info("Komga 功能已启用，正在启动通知监听器...")
                start_notification_process()
            elif is_config_update:
                global_logger.info("配置已更新，正在重启 Komga 通知监听器以应用更改...")
                stop_notification_process()
                start_notification_process()

    app.config['HATH_TOGGLE'] = hath_toggle
    app.config['NH_TOGGLE'] = nh_toggle
    app.config['ARIA2_TOGGLE'] = aria2_toggle
    app.config['KOMGA_TOGGLE'] = komga_toggle
    app.config['CHECKING_CONFIG'] = False

    # 通知设置
    app.config['NOTIFICATION'] = config_data.get('notification', {})
    if app.config['NOTIFICATION'].get('enable'):
        global_logger.info("通知服务功能已启用")
    else:
        global_logger.info("通知服务功能未启用")
        
    # Openai 设置
    openai_config = config_data.get('openai', {})
    app.config['OPENAI_API_KEY'] = str(openai_config.get('api_key', '')).strip()
    app.config['OPENAI_BASE_URL'] = str(openai_config.get('base_url', '')).strip().rstrip('/')
    app.config['OPENAI_MODEL'] = str(openai_config.get('model', '')).strip()
    if app.config['OPENAI_API_KEY'] and app.config['OPENAI_BASE_URL'] and app.config['OPENAI_MODEL']:
        global_logger.info("OpenAI 配置已设置")
        app.config['OPENAI_TOGGLE'] = True
    else:

        app.config['OPENAI_TOGGLE'] = False
    
    # ComicInfo 设置
    app.config['COMICINFO'] = config_data.get('comicinfo', {})

    eh_translator = EhTagTranslator(enable_translation=app.config.get('TAGS_TRANSLATION', True))
    metadata_extractor = MetadataExtractor(app.config, eh_translator)

    # 从数据库加载 eh_funds
    eh_funds_json = task_db.get_global_state('eh_funds')
    if eh_funds_json:
        try:
            app.config['EH_FUNDS'] = json.loads(eh_funds_json)
            global_logger.debug(f"从数据库加载 eh_funds: {app.config['EH_FUNDS']}")
        except json.JSONDecodeError:
            global_logger.error("从数据库加载 eh_funds 失败：无效的 JSON 格式")

def get_eh_mode(config, mode):
    aria2 = config.get('ARIA2_TOGGLE', False)
    hath = config.get('HATH_TOGGLE', (False, False))
    download_torrent = mode in ("torrent", "1") if mode else config.get('DOWNLOAD_TORRENT', True)
    if hath[0] and not aria2:
        return "archive"
    if aria2 and download_torrent:
        if hath[0]:
            return "both"
        else:
            return "torrent"
    elif hath[0]:
        return "archive"
    return "both"

def send_to_aria2(url=None, torrent=None, dir=None, out=None, logger=None, task_id=None):
    # 检查任务是否被取消
    if task_id:
        check_task_cancelled(task_id)

    rpc = aria2.Aria2RPC(app.config.get('ARIA2_SERVER'), app.config.get('ARIA2_TOKEN'))
    if url != None:
        result = rpc.add_uri(url, dir=dir, out=out)
        if logger: logger.info(result)
    elif torrent != None:
        result = rpc.add_torrent(torrent, dir=dir, out=out)
        if not app.config.get('KEEP_TORRENTS') == True:
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
            local_file_path = os.path.join(app.config.get('REAL_DOWNLOAD_DIR'), filename)
        else:
            local_file_path = os.path.join(app.config.get('REAL_DOWNLOAD_DIR'), os.path.basename(os.path.dirname(file)))

    # 完成下载后, 为压缩包添加元数据
    if os.path.exists(file):
        print(f"下载完成: {local_file_path}")
        if logger: logger.info(f"下载完成: {local_file_path}")
    return local_file_path


def sanitize_filename(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', s)

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
    if app.config['NOTIFICATION'].get('enable'):
        event_data = {
            "url": url,
            "task_id": task_id,
            "metadata": result,
            }
        notify(event="task.complete", data=event_data, logger=logger, notification_config=app.config['NOTIFICATION'])

def post_download_processing(dl, metadata, task_id, logger=None, is_nhentai=False):
    try:
        # 检查是否被取消
        check_task_cancelled(task_id)

        if not dl:
            return None

        # 创建 ComicInfo.xml 并转换为 CBZ
        if metadata.get('Writer') or metadata.get('Tags'):
            # 准备一个包含所有可用字段的字典，用于格式化
            template_vars = {k.lower(): v for k, v in metadata.items()}
            template_vars['filename'] = os.path.basename(dl)
            
            def finalize_none(value):
                return "" if value is None else value
            
            jinja_env = jinja2.Environment(finalize=finalize_none)

            def render_template(template_string):
                try:
                    template = jinja_env.from_string(template_string)
                    rendered_value = template.render(template_vars)
                    # 如果渲染结果是空字符串，也当作 None 处理
                    return rendered_value if rendered_value else None
                except Exception as e:
                    (logger.warning if logger else print)(f"Jinja2 模板渲染失败: {e}")
                    # 任何渲染失败都直接返回 None
                    return None

            # 根据 comicinfo 配置生成新的 metadata
            comicinfo_metadata = {}
            comicinfo_config = app.config.get('COMICINFO', {}) or {}

            # 定义一个从 config.yaml 中的小写键到 ComicInfo.xml 驼峰键的映射
            key_map = {
                'title': 'Title',
                'writer': 'Writer',
                'penciller': 'Penciller',
                'translator': 'Translator',
                'tags': 'Tags',
                'web': 'Web',
                'agerating': 'AgeRating',
                'manga': 'Manga',
                'genre': 'Genre',
                'languageiso': 'LanguageISO',
                'alternateseries': 'AlternateSeries'
            }

            for key, value_template in comicinfo_config.items():
                if isinstance(value_template, str) and value_template:
                    formatted_value = render_template(value_template)
                    # 只有当格式化后的值不是 None 时才添加
                    if formatted_value is not None:
                        # 使用映射转换键, 如果键在映射中不存在, 则默认将其首字母大写
                        camel_key = key_map.get(key, key.capitalize())
                        comicinfo_metadata[camel_key] = formatted_value
            if logger: logger.info(f"生成的 ComicInfo 元数据: {comicinfo_metadata}")

            # 用于渲染路径的变量无法接受 None 值，因此在 comicinfo_metadata 完成之后，再添加回退机制
            template_vars['author'] = metadata.get('Penciller') or metadata.get('Writer') or None
            template_vars['series'] = metadata.get('Series') or app.config.get('KOMGA_ONESHOT') or None


            move_path_template = app.config.get('MOVE_PATH')
            if move_path_template:
                # 为移动路径创建一个特殊的、健壮的 Jinja2 环境
                class UnknownUndefined(jinja2.Undefined):
                    def __str__(self):
                        return 'Unknown'
                
                def finalize_for_path(value):
                    # 此函数处理值为 None 或 "" 的情况
                    return value if value else 'Unknown'

                jinja_env_for_path = jinja2.Environment(
                    undefined=UnknownUndefined, # 处理不存在的键
                    finalize=finalize_for_path     # 处理 None 或 "" 的值
                )
                
                try:
                    path_template = jinja_env_for_path.from_string(move_path_template)
                    move_file_path = path_template.render(template_vars)
                    # 关键检查：处理渲染结果为空（例如模板是""）的情况
                    if not move_file_path:
                        (logger.warning if logger else print)(f"移动路径模板渲染结果为空, 回退到默认目录")
                        move_file_path = os.path.dirname(dl)
                except Exception as e:
                    (logger.warning if logger else print)(f"移动路径模板渲染失败: {e}, 回退到默认目录")
                    move_file_path = os.path.dirname(dl)
            else:
                move_file_path = os.path.dirname(dl)

            if not os.path.basename(move_file_path).lower().endswith(('.zip', '.cbz')):
                move_file_path = os.path.join(move_file_path, os.path.basename(dl))

            cbz = cbztool.write_xml_to_zip(dl, comicinfo_metadata, app=app, logger=logger)
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
        if app.config['KOMGA_TOGGLE'] and is_valid_zip(dl):
            if app.config['KOMGA_LIBRARY_ID']:
                kmg = komga.KomgaAPI(server=app.config['KOMGA_SERVER'], username=app.config['KOMGA_USERNAME'], password=app.config['KOMGA_PASSWORD'], logger=logger)
                if app.config['KOMGA_LIBRARY_ID']:
                    kmg.scan_library(app.config['KOMGA_LIBRARY_ID'])

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
        gallery_tool = nhentai.NHentaiTools(cookie=app.config.get('NHENTAI_COOKIE'), logger=logger)
    else:
        gallery_tool = ehentai.EHentaiTools(cookie=app.config.get('EH_COOKIE'), logger=logger)

    # 获取画廊元数据
    gmetadata = gallery_tool.get_gmetadata(url)
    
    # 在获得 gmetadata 后，触发 task.start 事件
    if app.config['NOTIFICATION'].get('enable'):
        if logger: logger.info("发送 task.start 通知")
        event_data = {
            "url": url,
            "task_id": task_id,
            "gmetadata": gmetadata,
        }
        notify(event="task.start", data=event_data, logger=logger, notification_config=app.config['NOTIFICATION'])
    
    if not gmetadata or 'gid' not in gmetadata:
        raise ValueError("Failed to retrieve valid gmetadata for the given URL.")
    # 获取标题
    if gmetadata.get('title_jpn'):
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
        # exhentai 限定的画廊在一些情况下能被 e-hentai 检索，但并不能通过 e-hentai 访问，因此当 exhentai 可用时，积极替换成 exhentai 的链接。
        eh_valid, exh_valid, eh_funds = gallery_tool.is_valid_cookie()
        if exh_valid: url = url.replace("e-hentai.org", "exhentai.org")
        else: url = url.replace("exhentai.org", "e-hentai.org")     
        # 顺便更新 GP 余额
        update_eh_funds(eh_funds)
        result = gallery_tool.get_download_link(url=url, mode=eh_mode)

        check_task_cancelled(task_id)

        if result:
            if result[0] == 'torrent':
                dl = send_to_aria2(torrent=result[1], dir=app.config.get('ARIA2_DOWNLOAD_DIR'), out=filename, logger=logger, task_id=task_id)
                if dl is None:
                    # 死种尝试 archive
                    result = gallery_tool.get_download_link(url=url, mode='archive')
                    dl = send_to_aria2(url=result[1], dir=app.config.get('ARIA2_DOWNLOAD_DIR'), out=filename, logger=logger, task_id=task_id)
            elif result[0] == 'archive':
                if not app.config.get('ARIA2_TOGGLE'):
                    dl = gallery_tool._download(
                        url=result[1],
                        path=path,
                        task_id=task_id,
                        tasks=tasks,
                        tasks_lock=tasks_lock
                    )
                else:
                    dl = send_to_aria2(url=result[1], dir=app.config.get('ARIA2_DOWNLOAD_DIR'), out=filename, logger=logger, task_id=task_id)

    check_task_cancelled(task_id)
    
    # 处理元数据
    metadata = metadata_extractor.parse_gmetadata(gmetadata, logger=logger)
    metadata['Web'] = url
    
    # 统一后处理
    final_path = post_download_processing(dl, metadata, task_id, logger, is_nhentai=is_nhentai)
    
    # 验证处理结果
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
    
def task_failure_processing(url, task_id, logger, tasks_lock, tasks):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e)
                if "cancelled by user" in error_msg:
                    if logger: logger.info(f"Task {task_id} was cancelled by user")
                    with tasks_lock:
                        if task_id in tasks:
                            tasks[task_id].status = TaskStatus.CANCELLED
                    # 更新数据库状态
                    from database import task_db
                    task_db.update_task(task_id, status=TaskStatus.CANCELLED)
                else:
                    if logger: logger.error(f"Task {task_id} failed with error: {e}")
                    with tasks_lock:
                        if task_id in tasks:
                            tasks[task_id].status = TaskStatus.ERROR
                            tasks[task_id].error = str(e)
                    # 更新数据库状态
                    from database import task_db
                    task_db.update_task(task_id, status=TaskStatus.ERROR, error=str(e))
                    
                    # 在获得 gmetadata 后，触发 task.start 事件
                    if app.config['NOTIFICATION'].get('enable'):
                        event_data = {
                            "task_id": task_id,
                            "url": url,
                            "error": str(e)
                        }
                        notify(event="task.error", data=event_data, logger=logger, notification_config=app.config['NOTIFICATION'])
                raise e
        return wrapper
    return decorator

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
    decorated_download_task = task_failure_processing(url, task_id, logger, tasks_lock, tasks)(download_task)
    
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
        'hath_toggle': app.config.get('HATH_TOGGLE', (False, False)),
        'nh_toggle': app.config.get('NH_TOGGLE', False),
        'aria2_toggle': app.config.get('ARIA2_TOGGLE', False),
        'komga_toggle': app.config.get('KOMGA_TOGGLE', False),
        'notification_toggle': notification_process is not None and notification_process.poll() is None,
        'notification_pid': notification_process.pid if notification_process and notification_process.poll() is None else None,
        'eh_funds': app.config.get('EH_FUNDS', {'GP': '-'})
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

    app.config['CHECKING_CONFIG'] = True
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
    # 提前判断并设置调试模式，这对于防止 reloader 重复执行副作用至关重要
    is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER', False)
    debug_mode = not is_docker
    app.debug = debug_mode

    # 在加载配置前，先执行迁移脚本
    migrate_ini_to_yaml()
    # 初始化时加载配置，确保端口号等信息在两个进程中都可用
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
        # 使用已经计算好的 debug_mode 来运行应用
        app.run(host='0.0.0.0', port=app.config.get('PORT', 5001), debug=app.debug)
    finally:
        executor.shutdown()
        # 确保在主应用终止时关闭子进程
        stop_notification_process()
