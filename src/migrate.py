import configparser
import os
import yaml

def lowercase_keys(obj):
    """递归地将字典中的所有键转换为小写。"""
    if isinstance(obj, dict):
        return {k.lower(): lowercase_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [lowercase_keys(elem) for elem in obj]
    return obj

def migrate_ini_to_yaml():
    """
    检查是否存在 config.ini 文件，如果存在，则将其配置合并到 config.yaml，
    然后将旧文件重命名以避免重复迁移。
    """
    config_dir = 'data'
    ini_path = os.path.join(config_dir, 'config.ini')
    yaml_path = os.path.join(config_dir, 'config.yaml')
    migrated_ini_path = os.path.join(config_dir, 'config.ini.migrated')

    # 只要 ini 文件存在，就执行迁移
    if os.path.exists(ini_path):
        print(f"'{ini_path}' found. Merging into '{yaml_path}'...")
        try:
            # 1. 读取 ini 配置
            config = configparser.ConfigParser(interpolation=None)
            config.optionxform = str
            config.read(ini_path, encoding='utf-8')
            ini_config_raw = {section: dict(config.items(section)) for section in config.sections()}
            ini_config = lowercase_keys(ini_config_raw)

            # 排除 notification 部分，以使用新的默认值
            if 'notification' in ini_config:
                del ini_config['notification']

            # 2. 读取现有的 yaml 配置（如果存在）
            existing_yaml_config = {}
            if os.path.exists(yaml_path):
                with open(yaml_path, 'r', encoding='utf-8') as yaml_file:
                    existing_yaml_config = yaml.safe_load(yaml_file) or {}

            # 3. 合并配置（ini 配置优先）
            # 使用深层合并
            def deep_merge(dict1, dict2):
                for k, v in dict2.items():
                    if k in dict1 and isinstance(dict1[k], dict) and isinstance(v, dict):
                        dict1[k] = deep_merge(dict1[k], v)
                    else:
                        dict1[k] = v
                return dict1

            merged_config = deep_merge(existing_yaml_config, ini_config)

            # 4. 写回 yaml 文件
            with open(yaml_path, 'w', encoding='utf-8') as yaml_file:
                for i, (section, data) in enumerate(merged_config.items()):
                    if i > 0:
                        yaml_file.write('\n')
                    yaml.dump({section: data}, yaml_file, allow_unicode=True, sort_keys=False)
            
            # 5. 重命名 ini 文件
            os.rename(ini_path, migrated_ini_path)
            print(f"Migration successful. '{ini_path}' has been renamed to '{migrated_ini_path}'.")

        except Exception as e:
            print(f"Error migrating config file: {e}")

if __name__ == '__main__':
    # 允许直接运行此脚本进行测试
    migrate_ini_to_yaml()