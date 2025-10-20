import os, json, re
import zipfile
import unicodedata
import logging
from logging.handlers import RotatingFileHandler
from glob import glob
from enum import Enum

class TaskStatus(str, Enum):
    IN_PROGRESS = "进行中"
    COMPLETED = "完成"
    CANCELLED = "取消"
    ERROR = "错误"
    @classmethod
    def all(cls):
        return [item.value for item in cls]
    

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

# 验证 ZIP 文件完整性
def is_valid_zip(path: str) -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return zf.testzip() is None
    except (FileNotFoundError, zipfile.BadZipFile):
        return False

# 移除字符串中的表情符号
def remove_emoji(text):
    return ''.join(
        c for c in text
        if not unicodedata.category(c).startswith('So')
    )

def extract_parody(text, translator):
    # 匹配末尾是 (xxx) [后缀] [后缀]... 的情况，提取 () 内内容
    match = re.search(r'\((?!\d+$)([^)]+)\)\s*(?:\[[^\]]+\]\s*)+$', text)
    if match:
        parody = match.group(1).strip()
    else:
        # 匹配末尾直接是 () 的情况
        match = re.search(r'\((?!\d+$)([^)]+)\)\s*$', text)
        parody = match.group(1).strip().lower() if match else None

    if parody:
        # 拆分日文顿号并去掉每个部分前后空格
        if '、' in parody:
            parts = [part.strip() for part in parody.split('、')]
            # 分别翻译
            translated_parts = [translator.get_translation(part.strip(), 'parody') for part in parts]
            parody_translated = ', '.join(translated_parts)
        else:
            parody_translated = translator.get_translation(parody.strip(), 'parody')
        return parody_translated
    return None



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

def parse_gallery_url(url: str) -> tuple[int | None, str | None]:
    """从 E-Hentai/ExHentai 画廊 URL 中解析 gid 和 token"""
    if not isinstance(url, str):
        return None, None
    match = re.search(r'/g/(\d+)/([a-f0-9]{10})', url)
    if match:
        gid = int(match.group(1))
        token = match.group(2)
        return gid, token
    return None, None
