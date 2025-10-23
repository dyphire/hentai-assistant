#!/usr/bin/env python3
"""
测试脚本：查看 eh_favorites 表中的数据
"""
import sys
import os
from datetime import datetime

# 添加父目录到路径以便导入模块
sys.path.append('src')

from database import TaskDatabase

def format_boolean(value):
    """格式化布尔值显示"""
    if value is None:
        return "NULL"
    return "是" if value else "否"

def format_datetime(value):
    """格式化日期时间显示"""
    if not value:
        return "NULL"
    try:
        # 尝试解析 ISO 格式的日期时间
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return value

def print_separator(length=120):
    """打印分隔线"""
    print("=" * length)

def print_favorites_table(favorites):
    """以表格形式打印收藏夹数据"""
    if not favorites:
        print("没有找到任何收藏夹数据")
        return
    
    print(f"\n找到 {len(favorites)} 条收藏夹记录：\n")
    print_separator()
    
    # 打印表头
    header = f"{'GID':<12} {'Token':<12} {'分类':<6} {'已下载':<8} {'Komga ID':<25} {'添加时间':<20}"
    print(header)
    print(f"{'Komga 标题 (title)':<80}")
    print(f"{'原始标题 (originaltitle)':<80}")
    print_separator()
    
    # 打印每条记录
    for fav in favorites:
        gid = str(fav.get('gid', 'N/A'))
        token = fav.get('token', 'N/A')[:10] + '..'
        favcat = str(fav.get('favcat', 'N/A'))
        downloaded = format_boolean(fav.get('downloaded'))
        komga = fav.get('komga', 'NULL')[:23] if fav.get('komga') else 'NULL'
        added = format_datetime(fav.get('added'))
        title = fav.get('title', 'N/A') if fav.get('title') else 'NULL'
        originaltitle = fav.get('originaltitle', 'N/A') if fav.get('originaltitle') else 'NULL'
        
        # 截断标题以适应显示
        title_display = title[:78] if len(title) > 78 else title
        originaltitle_display = originaltitle[:78] if len(originaltitle) > 78 else originaltitle
        
        print(f"{gid:<12} {token:<12} {favcat:<6} {downloaded:<8} {komga:<25} {added:<20}")
        print(f"{title_display:<80}")
        print(f"{originaltitle_display:<80}")
        print("-" * 120)

def print_statistics(db):
    """打印统计信息"""
    print("\n" + "=" * 50)
    print("统计信息")
    print("=" * 50)
    
    conn = db._get_conn()
    cursor = conn.cursor()
    
    # 总记录数
    cursor.execute("SELECT COUNT(*) FROM eh_favorites")
    total = cursor.fetchone()[0]
    print(f"总记录数: {total}")
    
    # 已下载数量
    cursor.execute("SELECT COUNT(*) FROM eh_favorites WHERE downloaded = 1")
    downloaded = cursor.fetchone()[0]
    print(f"已下载: {downloaded}")
    
    # 未下载数量
    cursor.execute("SELECT COUNT(*) FROM eh_favorites WHERE downloaded = 0 OR downloaded IS NULL")
    undownloaded = cursor.fetchone()[0]
    print(f"未下载: {undownloaded}")
    
    # 有 Komga ID 的数量
    cursor.execute("SELECT COUNT(*) FROM eh_favorites WHERE komga IS NOT NULL")
    with_komga = cursor.fetchone()[0]
    print(f"已上传到 Komga: {with_komga}")
    
    # 按分类统计
    cursor.execute("SELECT favcat, COUNT(*) FROM eh_favorites GROUP BY favcat ORDER BY favcat")
    favcat_stats = cursor.fetchall()
    if favcat_stats:
        print("\n按分类统计:")
        for favcat, count in favcat_stats:
            favcat_name = favcat if favcat is not None else "未分类"
            print(f"  分类 {favcat_name}: {count} 条")
    
    # 最新添加时间
    latest = db.get_latest_added_time()
    if latest:
        print(f"\n最新收藏时间: {format_datetime(latest)}")
    
    conn.close()
    print("=" * 50 + "\n")

def main():
    """主函数"""
    print("\n" + "=" * 50)
    print("E-Hentai 收藏夹数据查看工具")
    print("=" * 50 + "\n")
    
    # 初始化数据库
    db_path = './data/tasks.db'
    if not os.path.exists(db_path):
        print(f"错误: 数据库文件不存在: {db_path}")
        return
    
    db = TaskDatabase(db_path)
    
    # 打印统计信息
    print_statistics(db)
    
    # 获取所有收藏夹数据
    print("\n查询选项:")
    print("1. 查看所有收藏")
    print("2. 查看未下载的收藏")
    print("3. 查看已下载的收藏")
    print("4. 查看没有 Komga ID 的收藏")
    print("5. 按 GID 查询")
    print("6. 按分类查询")
    
    choice = input("\n请选择 (1-6，直接回车默认为1): ").strip() or "1"
    
    conn = db._get_conn()
    conn.row_factory = lambda cursor, row: dict(zip([col[0] for col in cursor.description], row))
    cursor = conn.cursor()
    
    if choice == "1":
        # 查看所有收藏
        cursor.execute("SELECT * FROM eh_favorites ORDER BY added DESC")
        favorites = cursor.fetchall()
        print_favorites_table(favorites)
        
    elif choice == "2":
        # 查看未下载的收藏
        favorites = db.get_undownloaded_favorites()
        print(f"\n未下载的收藏:")
        print_favorites_table(favorites)
        
    elif choice == "3":
        # 查看已下载的收藏
        cursor.execute("SELECT * FROM eh_favorites WHERE downloaded = 1 ORDER BY added DESC")
        favorites = cursor.fetchall()
        print(f"\n已下载的收藏:")
        print_favorites_table(favorites)
        
    elif choice == "4":
        # 查看没有 Komga ID 的收藏
        favorites = db.get_favorites_without_komga_id()
        print(f"\n没有 Komga ID 的收藏:")
        print_favorites_table(favorites)
        
    elif choice == "5":
        # 按 GID 查询
        gid_input = input("请输入 GID: ").strip()
        try:
            gid = int(gid_input)
            favorite = db.get_eh_favorite_by_gid(gid)
            if favorite:
                print_favorites_table([favorite])
            else:
                print(f"\n未找到 GID 为 {gid} 的收藏")
        except ValueError:
            print("错误: 请输入有效的数字 GID")
            
    elif choice == "6":
        # 按分类查询
        favcat_input = input("请输入分类 ID (用逗号分隔多个分类): ").strip()
        favcat_list = [f.strip() for f in favcat_input.split(',')]
        favorites = db.get_eh_favorites_by_favcat(favcat_list)
        print(f"\n分类 {favcat_input} 的收藏:")
        print_favorites_table(favorites)
    
    else:
        print("无效的选择")
    
    conn.close()

if __name__ == '__main__':
    main()