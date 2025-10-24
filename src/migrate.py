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

def migrate_cookie_to_credentials():
    """
    检查 config.yaml 中的 ehentai.cookie 字段，如果存在完整cookie字符串，
    则提取 ipb_member_id 和 ipb_pass_hash，写入配置并删除旧的 cookie 字段。
    """
    config_dir = 'data'
    yaml_path = os.path.join(config_dir, 'config.yaml')
    
    if not os.path.exists(yaml_path):
        return
    
    try:
        # 读取 yaml 配置
        with open(yaml_path, 'r', encoding='utf-8') as yaml_file:
            config = yaml.safe_load(yaml_file) or {}
        
        ehentai = config.get('ehentai', {})
        cookie_str = ehentai.get('cookie', '')
        
        # 如果没有 cookie 字段或已经有 ipb_member_id，则跳过
        if not cookie_str or ehentai.get('ipb_member_id'):
            return
        
        print(f"检测到旧的 E-Hentai cookie 格式，正在迁移...")
        
        # 从 cookie 字符串中提取 ipb_member_id 和 ipb_pass_hash
        ipb_member_id = None
        ipb_pass_hash = None
        
        for item in cookie_str.split(';'):
            if '=' in item:
                key, value = item.strip().split('=', 1)
                key = key.strip()
                value = value.strip()
                
                if key == 'ipb_member_id':
                    ipb_member_id = value
                elif key == 'ipb_pass_hash':
                    ipb_pass_hash = value
        
        # 如果成功提取到两个关键cookie，则更新配置
        if ipb_member_id and ipb_pass_hash:
            ehentai['ipb_member_id'] = ipb_member_id
            ehentai['ipb_pass_hash'] = ipb_pass_hash
            # 删除旧的 cookie 字段
            if 'cookie' in ehentai:
                del ehentai['cookie']
            
            config['ehentai'] = ehentai
            
            # 写回 yaml 文件
            with open(yaml_path, 'w', encoding='utf-8') as yaml_file:
                for i, (section, data) in enumerate(config.items()):
                    if i > 0:
                        yaml_file.write('\n')
                    yaml.dump({section: data}, yaml_file, allow_unicode=True, sort_keys=False)
            
            print(f"E-Hentai cookie 迁移成功: ipb_member_id={ipb_member_id}")
        else:
            print("无法从 cookie 字符串中提取 ipb_member_id 和 ipb_pass_hash")
    
    except Exception as e:
        print(f"迁移 E-Hentai cookie 时出错: {e}")

def migrate_listen_categories_to_favcat_whitelist():
    """
    检查 config.yaml 中的 ehentai.listen_categories 字段，如果存在，
    则将其从字符串格式迁移为 favcat_whitelist 列表格式。
    """
    config_dir = 'data'
    yaml_path = os.path.join(config_dir, 'config.yaml')
    
    if not os.path.exists(yaml_path):
        return
    
    try:
        # 读取 yaml 配置
        with open(yaml_path, 'r', encoding='utf-8') as yaml_file:
            config = yaml.safe_load(yaml_file) or {}
        
        ehentai = config.get('ehentai', {})
        
        # 如果已经有 favcat_whitelist 或没有 listen_categories，则跳过
        if 'favcat_whitelist' in ehentai or 'listen_categories' not in ehentai:
            return
        
        print(f"检测到旧的 listen_categories 配置，正在迁移到 favcat_whitelist...")
        
        listen_categories = ehentai.get('listen_categories', '')
        
        # 转换为列表格式
        if isinstance(listen_categories, list):
            # 如果已经是列表，直接重命名
            favcat_whitelist = [str(cat).strip() for cat in listen_categories]
        elif isinstance(listen_categories, str):
            # 如果是字符串
            if listen_categories.strip() == '':
                # 空字符串 -> 空列表（表示所有）
                favcat_whitelist = []
            else:
                # "0,1,2" -> [0, 1, 2]
                favcat_whitelist = [int(cat.strip()) for cat in listen_categories.split(',') if cat.strip().isdigit()]
        else:
            # 其他类型，设为空列表
            favcat_whitelist = []
        
        # 添加新字段并删除旧字段
        ehentai['favcat_whitelist'] = favcat_whitelist
        del ehentai['listen_categories']
        
        config['ehentai'] = ehentai
        
        # 写回 yaml 文件
        with open(yaml_path, 'w', encoding='utf-8') as yaml_file:
            for i, (section, data) in enumerate(config.items()):
                if i > 0:
                    yaml_file.write('\n')
                yaml.dump({section: data}, yaml_file, allow_unicode=True, sort_keys=False)
        
        print(f"listen_categories 迁移成功: {listen_categories} -> favcat_whitelist: {favcat_whitelist}")
    
    except Exception as e:
        print(f"迁移 listen_categories 时出错: {e}")

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
    
    # 在 ini 迁移后，执行其他迁移
    migrate_cookie_to_credentials()
    migrate_listen_categories_to_favcat_whitelist()

if __name__ == '__main__':
    # 允许直接运行此脚本进行测试
    migrate_ini_to_yaml()