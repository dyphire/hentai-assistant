#!/usr/bin/env python3
"""
独立脚本：强制刷新 male_only_taglist.json
从 ehwiki.org 的 Fetish Listing 页面提取带有 ♂ 标记的标签
直接覆盖现有文件，无需确认
"""

import os
import json
import requests
from bs4 import BeautifulSoup


def check_dirs(path):
    """确保目录存在，如果不存在则创建"""
    if not os.path.exists(path):
        os.makedirs(path)
    return path


def generate_male_only_taglist():
    """强制刷新 male_only_taglist.json"""
    print("开始强制刷新 male_only_taglist...")
    
    # 设置路径
    data_dir = check_dirs(os.path.join("data", "ehentai"))
    tags_dir = check_dirs(os.path.join(data_dir, "tags"))
    json_path = os.path.join(tags_dir, "male_only_taglist.json")
    
    m_list = []
    
    # 直接从 ehwiki 下载并解析（不保存 HTML）
    print("正在从 ehwiki.org 下载 Fetish Listing 页面...")
    url = "https://ehwiki.org/wiki/Fetish_Listing"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            print("正在解析 HTML 内容...")
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 查找所有带有 "♂" 的 <a> 标签
            for a_tag in soup.find_all('a'):
                # 检查<a>标签后是否有 ♂
                if a_tag.next_sibling and "♂" in a_tag.next_sibling:
                    tag_name = a_tag.string.strip('\u200e') if a_tag.string else None
                    if tag_name:
                        m_list.append(tag_name)
        else:
            print(f"下载失败，状态码: {response.status_code}")
            return
    except Exception as e:
        print(f"下载出错: {e}")
        return
    
    # 保存到 JSON 文件
    with open(json_path, 'w', encoding='utf-8') as j:
        json.dump({"content": m_list}, j, indent=4, ensure_ascii=False)
    
    print(f"✓ 成功生成 {len(m_list)} 个 male-only 标签")
    print(f"✓ 已保存到: {json_path}")
    print(f"\n前 10 个标签示例:")
    for i, tag in enumerate(m_list[:10], 1):
        print(f"  {i}. {tag}")


if __name__ == "__main__":
    try:
        generate_male_only_taglist()
    except KeyboardInterrupt:
        print("\n操作已取消")
    except Exception as e:
        print(f"发生错误: {e}")
        import traceback
        traceback.print_exc()