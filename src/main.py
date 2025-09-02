import os, configparser, re, shutil
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string, redirect, url_for
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
from utils import check_dirs
import nfotool

app = Flask(__name__)
# 设置5001端口为默认端口
app.config['port'] = 5001

config_path = './data/config.ini'
config_parser = configparser.ConfigParser()

# 创建一个线程池用于并发处理任务
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

tasks = {}
tasks_lock = threading.Lock()

class TaskInfo:
    def __init__(self, future, logger, log_buffer):
        self.future = future
        self.logger = logger
        self.log_buffer = log_buffer
        self.status = "进行中"  # "完成"、"取消"、"错误"
        self.error = None

# 日志初始化
LOG_FILE = "./data/app.log"

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
    buffer_handler = logging.StreamHandler(log_buffer)
    formatter = logging.Formatter(f'%(asctime)s [%(levelname)s] [task:{task_id}] %(message)s')
    buffer_handler.setFormatter(formatter)

    logger = logging.getLogger(f"task_{task_id}")
    logger.setLevel(logging.INFO)
    # 避免重复添加 handler
    if not any(isinstance(h, logging.StreamHandler) and getattr(h, 'stream', None) == log_buffer for h in logger.handlers):
        logger.addHandler(buffer_handler)
    # 添加全局日志（带 taskid 前缀）
    class TaskIdFilter(logging.Filter):
        def filter(self, record):
            record.msg = f"[task:{task_id}] {record.msg}"
            return True
    for h in global_logger.handlers:
        if not any(isinstance(f, TaskIdFilter) for f in h.filters):
            h.addFilter(TaskIdFilter())
    return logger, log_buffer

def check_config():
    TRUE_VALUES = {'true', '1', 'yes', 'on'}
    config_parser.read(config_path, encoding='utf-8')
    app.config['keep_torrents'] = (
        config_parser.get('general', 'keep_torrents', fallback='false').lower() in TRUE_VALUES
    )
    app.config['keep_original_file'] = (
        config_parser.get('general', 'keep_original_file', fallback='false').lower() in TRUE_VALUES
    )
    app.config['remove_ads'] = (
        config_parser.get('general', 'remove_ads', fallback='false').lower() in TRUE_VALUES
    )
    # 测试 E-Hentai 的连接
    if 'cookie' in config_parser['ehentai'] and not config_parser['ehentai']['cookie'] == '':
        app.config['eh_cookie'] = {"cookie": config_parser['ehentai']['cookie']}
    else:
        app.config['eh_cookie'] = {"cookie": ""}
    eh = ehentai.EHentaiTools(cookie=app.config['eh_cookie'], logger=global_logger)
    hath_toggle = eh.is_valid_cookie()
    # 测试 Aria2 RPC 的连接
    if 'enable' in config_parser['aria2'] and config_parser['aria2']['enable'].lower() in ['true', '1', 'yes']:
        global_logger.info("开始测试 Aria2 RPC 的连接")
        app.config['aria2_server'] = config_parser['aria2']['server'].rstrip('/')
        app.config['aria2_token'] = config_parser['aria2']['token']
        if 'download_dir' in config_parser['aria2'] and not config_parser['aria2']['download_dir'] == '':
            app.config['aria2_download_dir'] = config_parser['aria2']['download_dir'].rstrip('/')
        else:
            app.config['aria2_download_dir'] = None
        if 'mapped_dir' in config_parser['aria2'] and not config_parser['aria2']['mapped_dir'] == '':
            app.config['real_download_dir'] = config_parser['aria2']['mapped_dir'].rstrip('/')
        else:
            app.config['real_download_dir'] = app.config['aria2_download_dir']
        rpc = aria2.Aria2RPC(url=app.config['aria2_server'] ,token=app.config['aria2_token'], logger=global_logger)
        try:
            result = rpc.get_global_stat()
            if 'result' in result:
                global_logger.info(result)
                global_logger.info("Aria2 RPC 连接正常")
                aria2_toggle = True
            else:
                global_logger.info(result)
                global_logger.error("Aria2 RPC 连接异常, 种子下载功能将不可用")
                aria2_toggle = False
        except Exception as e:
            global_logger.error(f"Aria2 RPC 连接异常: {e}")
            aria2_toggle = False
    else:
        global_logger.info("Aria2 RPC 功能未启用")
        aria2_toggle = False
    # 测试 Komga API 的连接
    if 'enable' in config_parser['komga'] and config_parser['komga']['enable'].lower() in ['true', '1', 'yes']:
        global_logger.info("开始测试 Komga API 的连接")
        app.config['komga_server'] = config_parser['komga']['server'].rstrip('/')
        app.config['komga_token'] = config_parser['komga']['token']
        app.config['komga_library_dir'] = config_parser['komga']['library_dir']
        app.config['komga_oneshot'] = config_parser['komga']['oneshot']
        app.config['komga_library_id'] = config_parser['komga']['library_id']
        kmg = komga.KomgaAPI(server=app.config['komga_server'], token=app.config['komga_token'], logger=global_logger)
        try:
            library = kmg.get_libraries(library_id=app.config['komga_library_id'])
            if library.status_code == 200:
                global_logger.info("Komga API 连接成功")
                komga_toggle = True
                global_logger.info("获取到以下库信息:")
                global_logger.info(f"{library.json()['name']} {library.json()['id']} {library.json()['root']}")
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
    app.config['aria2_toggle'] = aria2_toggle
    app.config['komga_toggle'] = komga_toggle
    app.config['checking_config'] = False

def send_to_aria2(url=None, torrent=None, dir=None, out=None, logger=None):
    rpc = aria2.Aria2RPC(app.config['aria2_server'], app.config['aria2_token'])
    if url != None:
        result = rpc.add_uri(url, dir=dir)
        if logger: logger.info(result)
    elif torrent != None:
        result = rpc.add_torrent(torrent, dir=dir, out=out)
        if not app.config['keep_torrents'] == True:
            os.remove(torrent)
        if logger: logger.info(result)
    gid = result['result']
    # 监视 aria2 的下载进度
    file = rpc.listen_status(gid)
    if file == None:
        if logger: logger.info("疑似为死种, 尝试用 Arichive 的方式下载")
        return None
    else:
        filename = os.path.basename(file)
        if filename.lower().endswith("zip"):
            local_file_path = os.path.join(app.config['aria2_download_dir'], filename)
        else:
            parent_dir = os.path.dirname(file)
            parent_name = os.path.basename(parent_dir)
            archive_name = os.path.join(app.config['aria2_download_dir'], parent_name + ".zip")
            # 打包父目录为 zip
            shutil.make_archive(
                base_name = os.path.splitext(archive_name)[0],
                format = "zip",
                root_dir = parent_dir,
                base_dir = "."
            )
            local_file_path = archive_name

    # 完成下载后, 为压缩包添加元数据
    if os.path.exists(file):
        print(f"下载完成: {local_file_path}")
        if logger: logger.info(f"下载完成: {local_file_path}")
    return local_file_path

def parse_eh_tags(tags):
    comicinfo = {'Genre':'Hentai', 'AgeRating':'R18+'}
    #char_list = []
    tag_list = []
    collectionlist = []
    for tag in tags:
        # 因为 komga 这样软件并不支持 EH Tag 的 namespace，照搬会显得很别扭，所以这里会像 nhentai 那样，将一些 tag 的 namespace 去除
        matchTag = re.match(r'(.+?):(.*)',tag)
        if matchTag:
            namespace = matchTag.group(1)
            tag_name = matchTag.group(2)
            if namespace == 'language':
                if not tag_name == 'translated': comicinfo['LanguageISO'] = langcodes.find(tag_name).language # 转换为BCP-47
            elif namespace == 'parody':
                # 提取 parody 内容至 SeriesGroup
                if not tag_name == 'original':
                    kanji_parody = ehentai.get_original_tag(tag_name) # 将提取到合集的 Tag 翻译为日文
                    tag_list.append(tag) #  此处保留 namespace，方便所有 parody 相关的 tag 能排序在一块
                    if not kanji_parody == None:
                        comicinfo['Genre'] = comicinfo['Genre'] + ', Parody'
                        collectionlist.append(kanji_parody)
            elif namespace in ['character']:
                tag_list.append(tag) # 保留 namespace，理由同 parody
            elif namespace == 'female' or namespace == 'mixed':
                tag_list.append(tag_name) # 去掉 namespace, 仅保留内容
            elif namespace == 'male': # male 与 female 存在相同的标签, 但它们在作品中表达的含义是不同的, 为了减少歧义，这里将会丢弃所有 male 相关的共同标签，但是保留 male 限定的标签
                if tag_name in ehentai.male_only_taglist():
                    tag_list.append(tag_name)
            elif namespace == 'other':
                #if not 'extraneous' in matchTag.group(2):
                tag_list.append(matchTag.group(2))
    # 进行以下去重
    tag_list_sorted = sorted(set(tag_list), key=tag_list.index)
    # 为 webtoon 以外的漫画指定翻页顺序
    if not 'webtoon' in tag_list_sorted:
        comicinfo['Manga'] = 'YesAndRightToLeft'
    comicinfo['Tags'] = ', '.join(tag_list_sorted)
    if not collectionlist == []: comicinfo['SeriesGroup'] = ', '.join(collectionlist)
    return comicinfo

# 解析来自 E-Hentai API 的画廊信息
def parse_gmetadata(data):
    comicinfo = {}
    if 'token' in data:
        comicinfo['Web'] = 'https://exhentai.org/g/{gid}/{token}/'.format(gid=data['gid'],token=data['token'])
    if 'tags' in data:
        comicinfo.update(parse_eh_tags(data['tags']))
    # 把 Manga 以外的 category 添加到 Tags，主要用途在于把 doujinshi 作为标签，方便在商业作中筛选
    if not data['category'] == 'Manga':
        if 'Tags' in comicinfo:
            comicinfo['Tags'] = comicinfo['Tags'] + ', ' + data['category'].lower()
        else:
            comicinfo['Tags'] = data['category'].lower()
    # 从标题中提取作者信息
    if not data['title_jpn'] == "": text = data['title_jpn']
    else: text = data['title']
    comicinfo['Title'], comicinfo['Writer'], comicinfo['Penciller'] = ehentai.parse_filename(text)
    if comicinfo['Writer'] == None:
        if 'tags' in data:
            artists = [t.split(":", 1)[1] for t in data['tags'] if t.startswith("artist:")]
            if artists:
                comicinfo['Writer'] = ", ".join(artists)
    if comicinfo['Penciller'] == None:
        if 'tags' in data:
            groups = [t.split(":", 1)[1] for t in data['tags'] if t.startswith("group:")]
            if groups:
                comicinfo['Penciller'] = ", ".join(groups)
    return comicinfo

def download_task(url, task_id, logger=None):
    try:
        if logger: logger.info(f"Task {task_id} started, downloading from: {url}")
        eh = ehentai.EHentaiTools(cookie=app.config['eh_cookie'], logger=logger)
        gmetadata = eh.get_gmetadata(url)
        filename = gmetadata['title_jpn'] + ' [' + f'{gmetadata['gid']}' + ']' + '.zip'
        # 根据功能启用情况设置下载模式
        if app.config['aria2_toggle'] and not app.config['hath_toggle']:
            eh_mode = "torrent"
        elif not app.config['aria2_toggle'] and app.config['hath_toggle']:
            eh_mode = "archive"
        elif app.config['aria2_toggle'] and app.config['hath_toggle']:
            eh_mode = "both"
        result = eh.archive_download(url=url, mode=eh_mode)
        if result:
            if result[0] == 'torrent':
                dl = send_to_aria2(torrent=result[1], dir=app.config['aria2_download_dir'], out=filename)
                if dl == None:
                    result = eh.archive_download(url=url, mode='archive')
            elif result[0] == 'archive':
                if eh_mode == "archive":
                    # 通过 ehentai 的 session 直接下载
                    dl = eh._download(url=result[1], dir=check_dirs('./data/download/ehentai'))
                else:
                    dl = send_to_aria2(url=result[1], dir=app.config['aria2_download_dir'], out=filename)
            if dl:
                ml = os.path.join(app.config['real_download_dir'], os.path.basename(dl))
                # 将 gmetadata 转换为兼容 comicinfo 的形式
                metadata = parse_gmetadata(gmetadata)
                if metadata['Writer']:
                    cbz = nfotool.write_xml_to_zip(dl, ml, metadata, app=app, logger=logger)

                # 将文件移动到 Komga 媒体库
                # 当带有 multi-work series 标签时, 将 metadata['Series'] 作为系列，否则统一使用 oneshot
                if app.config['komga_toggle']:
                    if cbz and app.config['komga_library_dir']:
                        if 'Series' in metadata:
                            series = metadata['Series']
                        else:
                            series = app.config['komga_oneshot']
                        # 导入到 Komga
                        library_path = app.config['komga_library_dir']
                        destination = os.path.join(library_path, metadata['Penciller'], series)
                        if logger: logger.info(f"开始移动: {cbz} ==> {destination}")
                        result = shutil.move(cbz, check_dirs(destination))
                        if logger: logger.info("移动完毕")
                        kmg = komga.KomgaAPI(server=app.config['komga_server'], token=app.config['komga_token'], logger=logger)
                        if app.config['komga_library_id']:
                            kmg.scan_library(app.config['komga_library_id'])
        if logger: logger.info(f"Task {task_id} completed successfully.")
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id].status = "完成"
    except Exception as e:
        if logger: logger.error(f"Task {task_id} failed with error: {e}")
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id].status = "错误"
                tasks[task_id].error = str(e)

@app.route('/api/download', methods=['GET'])
def download_url():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    # 两位年份+月日时分秒
    task_id = datetime.now().strftime('%y%m%d%H%M%S%f')
    logger, log_buffer = get_task_logger(task_id)
    future = executor.submit(download_task, url, task_id, logger)
    with tasks_lock:
        tasks[task_id] = TaskInfo(future, logger, log_buffer)
    return jsonify({'message': f"Download task for {url} started with task ID {task_id}.", 'task_id': task_id}), 202

@app.route('/api/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    cancelled = task.future.cancel()
    if cancelled:
        with tasks_lock:
            task.status = "取消"
        return jsonify({'message': 'Task cancelled'})
    else:
        return jsonify({'message': 'Task could not be cancelled (可能已在运行或已完成)'})

@app.route('/api/task_log/<task_id>')
def get_task_log(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    log_content = task.log_buffer.getvalue()
    return jsonify({'log': log_content})

@app.route('/config', methods=['GET', 'POST'])
def show_config():
    config_parser = configparser.ConfigParser()
    config_parser.read(config_path, encoding='utf-8')
    edit_mode = request.args.get('edit') == '1'
    if request.method == 'POST':
        # 保存表单数据到 config.ini
        for section in config_parser.sections():
            for key in config_parser[section]:
                form_key = f"{section}__{key}"
                if form_key in request.form:
                    value = request.form[form_key]
                    # 如果包含分号或井号且未加引号，则加引号
                    if (';' in value or '#' in value) and not (value.startswith('"') and value.endswith('"')):
                        value = f'"{value}"'
                    config_parser[section][key] = value
        with open(config_path, 'w', encoding='utf-8') as f:
            config_parser.write(f, space_around_delimiters=False)
        # 标记正在检查
        app.config['checking_config'] = True
        # 启动检查（可用线程池或直接调用）
        executor.submit(check_config)
        return redirect(url_for('config_checking'))

    # 展示时去除首尾引号
    def safe_value(val):
        if val.startswith('"') and val.endswith('"'):
            return val[1:-1]
        return val

    def status_emoji(val):
        if val is True:
            return "✅"
        elif val is False:
            return "❌"
        else:
            return "⚠️"

    # 状态信息
    status_html = f'''
    <br>
    <b>E-Hentai: </b> {status_emoji(app.config['hath_toggle'])}
    <br>
    <b>Aria2: </b> {status_emoji(app.config['aria2_toggle'])}
    <br>
    <b>Komga: </b> {status_emoji(app.config['komga_toggle'])}
    <br>
    '''

    if not edit_mode:
        html = '''
        <h2>config.ini</h2>
        <form method="get">
        <button type="submit" name="edit" value="1">编辑</button>
        </form>
        <table border="1" cellpadding="5">
        {% for section in config.sections() %}
            <tr><th colspan="2" style="background:#eee">{{ section }}</th></tr>
            {% for key, value in config[section].items() %}
                <tr>
                    <td>{{ key }}</td>
                    <td>{{ safe_value(value) }}</td>
                </tr>
            {% endfor %}
        {% endfor %}
        </table>
        ''' + status_html
    else:
        html = '''
        <h2>配置文件内容（可编辑）</h2>
        <form method="post">
        <table border="1" cellpadding="5">
        {% for section in config.sections() %}
            <tr><th colspan="2" style="background:#eee">{{ section }}</th></tr>
            {% for key, value in config[section].items() %}
                <tr>
                    <td>{{ key }}</td>
                    <td>
                        <input type="text" name="{{ section }}__{{ key }}" value="{{ safe_value(value) }}" style="width:100%%">
                    </td>
                </tr>
            {% endfor %}
        {% endfor %}
        </table>
        <br>
        <input type="submit" value="保存">
        </form>
        ''' + status_html
    return render_template_string(html, config=config_parser, safe_value=safe_value)

@app.route('/config/checking')
def config_checking():
    html = '''
    <h2>正在重新检查配置，请稍候...</h2>
    <script>
    setTimeout(function(){
        window.location.href = "/config/check_status";
    }, 2000);
    </script>
    '''
    return html

@app.route('/config/check_status')
def config_check_status():
    # 检查是否完成
    if not app.config.get('checking_config', False):
        return redirect(url_for('show_config'))
    # 检查还未完成，继续等待
    html = '''
    <h2>正在重新检查配置，请稍候...</h2>
    <script>
    setTimeout(function(){
        window.location.reload();
    }, 2000);
    </script>
    '''
    return html

@app.route('/download')
def download_page():
    with tasks_lock:
        task_list = [
            {
                "id": tid,
                "status": t.status,
                "error": t.error,
            }
            for tid, t in tasks.items()
        ]
    html = '''
    <h2>下载任务列表</h2>
    <table border="1" cellpadding="5">
        <tr>
            <th>任务ID</th>
            <th>状态</th>
            <th>错误信息</th>
        </tr>
        {% for task in task_list %}
        <tr>
            <td>{{ task.id }}</td>
            <td>
                {% if task.status == "完成" %}
                    ✅ 完成
                {% elif task.status == "取消" %}
                    ❌ 取消
                {% elif task.status == "错误" %}
                    ⚠️ 错误
                {% else %}
                    ⏳ 进行中
                {% endif %}
            </td>
            <td>{{ task.error or "" }}</td>
        </tr>
        {% endfor %}
    </table>
    <br>
    <form method="get">
        <button type="submit">刷新</button>
    </form>
    '''
    return render_template_string(html, task_list=task_list)

if __name__ == '__main__':
    if not os.path.isfile(config_path):
        example_path = './data/config.ini'
        if os.path.isfile(example_path):
            shutil.copy(example_path, config_path)
            global_logger.info("未正确配置 config.ini。")
        else:
            global_logger.error("配置文件不存在，且未找到 config.ini.example，请手动创建 config.ini。")
            exit(1)
    else:
        check_config()
        try:
            app.run(host='0.0.0.0', port=app.config['port'], debug=True)
        finally:
            executor.shutdown()