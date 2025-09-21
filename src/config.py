# src/config.py
import configparser
import os

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
            'tags_translation': 'false',
            'prefer_japanese_title': 'true',
            'remove_ads': 'true',
            'move_path': ''
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
            'token': '',
            'library_id': '',
            'oneshot': '_oneshot'
        }
    }

def save_config(config_data):
    # 将配置数据保存到 config.ini 文件
    os.makedirs(CONFIG_DIR, exist_ok=True)
    
    config_to_save = {k: v for k, v in config_data.items() if k != 'status'}

    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            section_count = 0
            for section_name, section_data in config_to_save.items():
                if section_count > 0:
                    f.write('\n')
                f.write(f'[{section_name}]\n')
                for key, value in section_data.items():
                    if isinstance(value, bool):
                        f.write(f'{key}={str(value).lower()}\n')
                    elif isinstance(value, str) and (' ' in value or any(c in value for c in ['#', ';', '='])):
                        f.write(f'{key}="{value}"\n')
                    else:
                        f.write(f'{key}={value}\n')
                section_count += 1
    except Exception as e:
        print(f"Error saving config file: {e}")
        raise

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
