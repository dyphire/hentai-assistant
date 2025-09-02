import os, json, re
import logging
from logging.handlers import RotatingFileHandler
from glob import glob

def json_output(data):
    return json.dumps(data, indent=4, ensure_ascii=False)

# 检查目录是否存在
def check_dirs(path):
    if not os.path.exists(path):
        os.makedirs(path)
    return path

# 判断是否为 URL
def is_url(text):
    # 正则表达式用于匹配 URL
    url_pattern = re.compile(r'(https?://[^\s]+)')
    return re.match(url_pattern, text) is not None


'''def map_dir(path):
    if config.komga_mapped_dir == None:
        return path
    else:
        return path.replace(config.komga_path, config.komga_mapped_dir)'''

def get_task_logger(task_id=None):
    MAX_UUID_LOG_FILES = 5
    MAX_APP_LOG_FILES = 3
    LOG_DIR = "logs"
    os.makedirs(LOG_DIR, exist_ok=True)

    if task_id:
        # uuid 日志轮转，最多保留5个
        log_files = sorted(
            [f for f in glob(os.path.join(LOG_DIR, "*.log")) if not f.endswith("app.log")],
            key=os.path.getmtime
        )
        while len(log_files) >= MAX_UUID_LOG_FILES:
            os.remove(log_files[0])
            log_files = sorted(
                [f for f in glob(os.path.join(LOG_DIR, "*.log")) if not f.endswith("app.log")],
                key=os.path.getmtime
            )
        logger_name = str(task_id)
        log_path = os.path.join(LOG_DIR, f"{task_id}.log")
        mode = 'a'
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.handlers = []
        fh = logging.FileHandler(log_path, mode=mode, encoding='utf-8')
    else:
        # app.log 轮转，最多3份
        logger_name = "app"
        log_path = os.path.join(LOG_DIR, "app.log")
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.handlers = []
        fh = RotatingFileHandler(
            log_path,
            mode='a',
            maxBytes=2 * 1024 * 1024,  # 每个日志最大2MB，可根据需要调整
            backupCount=MAX_APP_LOG_FILES,
            encoding='utf-8'
        )

    file_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    fh.setFormatter(file_formatter)
    logger.addHandler(fh)

    # 控制台输出
    ch = logging.StreamHandler()
    console_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    ch.setFormatter(console_formatter)
    logger.addHandler(ch)

    return logger