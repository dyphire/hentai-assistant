# src/config.py
import yaml
import os
import logging
import sqlite3
from datetime import datetime, timezone

from providers import komga, aria2, ehentai, nhentai
from utils import TaskStatus

# 定义配置文件的路径
CONFIG_DIR = 'data'
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.yaml')

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
            'aggressive_series_detection': 'false', # 启用后，E-Hentai 会对 AltnateSeries 字段进行更激进的检测。
            'openai_series_detection': 'false' # 启用后，使用配置号的 OpenAI 接口对标题进行系列名和序号的检测。
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
            'notifiers': []
        },
        'openai': {
            'api_key': '',
            'base_url': '',
            'model': ''
        },
        'comicinfo': {
            'title': '{{title}}',
            'writer': '{{writer}}',
            'penciller': '{{penciller}}',
            'translator': '{{translator}}',
            'tags': '{{tags}}',
            'web': '{{web}}',
            'agerating': '{{agerating}}',
            'manga': '{{manga}}',
            'genre': '{{genre}}',
            'languageiso': '{{languageiso}}',
            'alternateseries': '{{series}}'
        }
    }

def save_config(config_data):
    # 将配置数据保存到 config.yaml 文件
    os.makedirs(CONFIG_DIR, exist_ok=True)
    config_to_save = {k: v for k, v in config_data.items() if k != 'status'}

    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as configfile:
            # 逐个 section 写入，并在它们之间添加空行以提高可读性
            for i, (section, data) in enumerate(config_to_save.items()):
                if i > 0:
                    configfile.write('\n')
                yaml.dump({section: data}, configfile, allow_unicode=True, sort_keys=False)
    except Exception as e:
        print(f"Error saving config file: {e}")
        raise

def lowercase_keys(obj):
    if isinstance(obj, dict):
        return {k.lower(): lowercase_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [lowercase_keys(elem) for elem in obj]
    return obj

def load_config():
    # 加载 config.yaml 文件，如果不存在则创建并使用默认值
    default_config = get_default_config()
    
    if not os.path.exists(CONFIG_PATH):
        print(f"'{CONFIG_PATH}' not found. Creating a new one with default settings.")
        save_config(default_config)
        return default_config
    
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as configfile:
            user_config_raw = yaml.safe_load(configfile) or {}
            if not isinstance(user_config_raw, dict):
                raise ValueError("Config file is not a valid dictionary.")
            user_config = lowercase_keys(user_config_raw)
    except Exception as e:
        print(f"Error reading or parsing config file '{CONFIG_PATH}', using default config: {e}")
        return default_config

    config_data = get_default_config()
    config_updated = False

    # 将用户配置合并到默认配置中
    for section, section_items in user_config.items():
        if section in config_data and isinstance(section_items, dict):
            for key, value in section_items.items():
                if key in config_data[section]:
                    config_data[section][key] = value
    
    # 检查并补充缺失的配置项
    default_config_for_check = get_default_config()
    for section, section_items in default_config_for_check.items():
        if section not in config_data:
            config_data[section] = section_items
            config_updated = True
        elif isinstance(section_items, dict):
            for key, value in section_items.items():
                if key not in config_data[section]:
                    config_data[section][key] = value
                    config_updated = True

    # 增强布尔值转换逻辑
    TRUE_VALUES = {'true', 'yes', 'on', '1'}
    FALSE_VALUES = {'false', 'no', 'off', '0'}

    for section in config_data:
        for key, value in config_data[section].items():
            if isinstance(value, str):
                lower_value = value.lower()
                if lower_value in TRUE_VALUES:
                    config_data[section][key] = True
                elif lower_value in FALSE_VALUES:
                    config_data[section][key] = False

    if config_updated:
        print(f"Config file '{CONFIG_PATH}' has been updated with missing entries.")
        save_config(config_data)

    return config_data