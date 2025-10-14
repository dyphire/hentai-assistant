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
        'GENERAL': {
            'PORT': '5001',
            'DOWNLOAD_TORRENT': 'false',
            'KEEP_TORRENTS': 'false',
            'KEEP_ORIGINAL_FILE': 'false',
            'PREFER_JAPANESE_TITLE': 'true',
            'MOVE_PATH': ''
        },
        'ADVANCED':{
            'TAGS_TRANSLATION': 'false',
            'REMOVE_ADS': 'false',
            'AGGRESSIVE_SERIES_DETECTION': 'false', # 启用后，E-Hentai 会对 AltnateSeries 字段进行更激进的检测。
            'OPENAI_SERIES_DETECTION': 'false' # 启用后，使用配置号的 OpenAI 接口对标题进行系列名和序号的检测。
        },
        'EHENTAI': {
            'COOKIE': ''
        },
        'NHENTAI': {
            'COOKIE': ''
        },
        'ARIA2': {
            'ENABLE': 'false',
            'SERVER': 'http://localhost:6800/jsonrpc',
            'TOKEN': '',
            'DOWNLOAD_DIR': '',
            'MAPPED_DIR': ''
        },
        'KOMGA': {
            'ENABLE': 'false',
            'SERVER': '',
            'USERNAME': '',
            'PASSWORD': '',
            'LIBRARY_ID': '',
            'ONESHOT': '_oneshot'
        },
        'NOTIFICATION': {
            'ENABLE': 'false',
            'APPRISE': '',
            'WEBHOOK': '',
            'TASK.START': '',
            'TASK.COMPLETE': '',
            'TASK.ERROR':'',
            'KOMGA.NEW':''
            
        },
        'OPENAI': {
            'API_KEY': '',
            'BASE_URL': '',
            'MODEL': ''
        },
        'COMICINFO': {
            'Title': '{{title}}',
            'Writer': '{{writer}}',
            'Penciller': '{{penciller}}',
            'Translator': '{{translator}}',
            'Tags': '{{tags}}',
            'Web': '{{web}}',
            'AgeRating': '{{agerating}}',
            'Manga': '{{manga}}',
            'Genre': '{{genre}}',
            'LanguageISO': '{{languageiso}}',
            'AlternateSeries': '{{series}}'
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
            config_data = {}
            # 读取 config.ini 并将所有 section 和 key 转换为大写，以实现兼容性
            for section in config.sections():
                upper_section = section.upper()
                if upper_section in default_config:
                    config_data[upper_section] = {}
                    for key, value in config.items(section):
                        upper_key = key.upper()
                        # 对于 NOTIFICATION 部分，加载所有键。对于其他部分，只加载默认配置中存在的键。
                        # COMICINFO 的键保持其在 default_config 中的原始大小写
                        if upper_section == 'NOTIFICATION':
                            config_data[upper_section][upper_key] = unquote_recursive(value)
                        elif upper_section == 'COMICINFO':
                            # 对于 ComicInfo，我们需要保留 default_config 中的原始键名大小写
                            # 找到匹配的原始键名
                            original_key = next((k for k in default_config[upper_section] if k.upper() == upper_key), None)
                            if original_key:
                                config_data[upper_section][original_key] = unquote_recursive(value)
                        elif upper_key in default_config[upper_section]:
                            if upper_key == 'COOKIE':
                                config_data[upper_section][upper_key] = unquote_recursive(value)
                            else:
                                config_data[upper_section][upper_key] = value

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
                # 对于 COMICINFO，键的比较是大小写敏感的
                if section == 'COMICINFO':
                    if key not in config_data[section]:
                        config_data[section][key] = value
                        config_updated = True
                else: # 对于其他 section，键的比较是大小写不敏感的
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