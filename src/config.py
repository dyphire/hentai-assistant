# src/config.py
import configparser
import os
import logging
import sqlite3
from datetime import datetime, timezone

from providers import komga, aria2, ehentai, nhentai
from utils import TaskStatus

# 定义配置文件的路径
CONFIG_DIR = 'data'
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.ini')

def get_default_config():
    return {
        'general': {
            'port': '5001',
            'download_torrent': 'false',
            'keep_torrents': 'false',
            'keep_original_file': 'false',
            'prefer_japanese_title': 'true',
            'move_path': ''
        },
        'advanced':{
            'tags_translation': 'false',
            'remove_ads': 'false',
            'ehentai_genre': 'false', # 将 E-Hentai 或 NHentai 的 Categories 作为 Genre 使用。设定为 false 时则统一使用 Hentai 作为 Genre。
            'aggressive_series_detection': 'false', # 启用后，E-Hentai 会对 AltnateSeries 字段进行更激进的检测。
        },
        'ehentai': {
            'cookie': ''
        },
        'nhentai': {
            'cookie': ''
        },
        'aria2': {
            'enable': 'false',
            'server': 'http://localhost:6800/jsonrpc',
            'token': '',
            'download_dir': '',
            'mapped_dir': ''
        },
        'komga': {
            'enable': 'false',
            'server': '',
            'username': '', 
            'password': '', 
            'library_id': '',
            'oneshot': '_oneshot'
        },
        'notification': {
            'enable': 'false',
            'apprise': '',
            'webhook': '',
            'task.start': '',
            'task.complete': '',
            'task.error':'',
            'komga.new':''   
            
        }
    }

def save_config(config_data):
    # 将配置数据保存到 config.ini 文件
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    config_to_save = {k: v for k, v in config_data.items() if k != 'status'}

    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str

    for section_name, section_data in config_to_save.items():
        config.add_section(section_name)
        for key, value in section_data.items():
            if isinstance(value, bool):
                config.set(section_name, key, str(value).lower())
            else:
                config.set(section_name, key, str(value))

    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
    except Exception as e:
        print(f"Error saving config file: {e}")
        raise

def unquote_recursive(s):
    if isinstance(s, str) and len(s) > 1 and s.startswith('"') and s.endswith('"'):
        return unquote_recursive(s[1:-1])
    return s

def load_config():
    # 加载 config.ini 文件，如果不存在则创建并使用默认值
    default_config = get_default_config()
    
    if not os.path.exists(CONFIG_PATH):
        print(f"'{CONFIG_PATH}' not found. Creating a new one with default settings.")
        save_config(default_config)
        config_data = default_config
    else:
        config = configparser.ConfigParser(interpolation=None)
        config.optionxform = str
        try:
            config.read(CONFIG_PATH, encoding='utf-8')
            # 只加载 default_config 中定义的键，忽略未知的键
            config_data = {}
            for section in config.sections():
                if section in default_config:
                    config_data[section] = {}
                    for key, value in config.items(section):
                        if key in default_config[section]:
                            if key == 'cookie':
                                config_data[section][key] = unquote_recursive(value)
                            else:
                                config_data[section][key] = value
        except Exception as e:
            print(f"Error reading config file '{CONFIG_PATH}', using default config: {e}")
            config_data = default_config

    # 对比模板，补充缺失的配置
    config_updated = False
    for section, section_items in default_config.items():
        if section not in config_data:
            config_data[section] = section_items
            config_updated = True
        else:
            for key, value in section_items.items():
                if key not in config_data[section]:
                    config_data[section][key] = value
                    config_updated = True

    if config_updated:
        print(f"Config file '{CONFIG_PATH}' has been updated with missing entries.")
        save_config(config_data)

    # 将配置文件中的 'true'/'false' 字符串转换为布尔值，方便前端处理
    for section in config_data:
        for key, value in config_data[section].items():
            if isinstance(value, str):
                if value.lower() == 'true':
                    config_data[section][key] = True
                elif value.lower() == 'false':
                    config_data[section][key] = False
    return config_data

def check_config(app, global_logger):
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
        app.config['komga_username'] = str(komga_config.get('username', ''))
        app.config['komga_password'] = str(komga_config.get('password', ''))
        app.config['komga_library_id'] = str(komga_config.get('library_id', ''))

        kmg = komga.KomgaAPI(server=app.config['komga_server'], username=app.config['komga_username'], password=app.config['komga_password'],  logger=global_logger)
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

    # 通知设置
    notification_config = config_data.get('notification', {})
    notification_enable = str(notification_config.get('enable', 'false')).lower() in TRUE_VALUES
    if notification_enable:
        global_logger.info("通知服务功能已启用")
        app.config['notify_toggle'] = True
        app.config['notify_apprise'] = str(notification_config.get('apprise', '')).strip() or None
        app.config['notify_webhook'] = str(notification_config.get('webhook', '')).strip() or None
        
        # 使用列表推导式正确处理通知事件
        notify_events = {}
        for e_key in ['task.start', 'task.complete', 'task.error',  'komga.new']:
            config_value = notification_config.get(e_key, '').strip()
            if config_value:
                # 分割并去除空白，然后添加到列表中
                notify_events[e_key] = [item.strip() for item in config_value.split(',') if item.strip()]
        app.config['notify_events'] = notify_events if notify_events else None
        print("通知事件设置为:", app.config['notify_events'])

    return config_data

