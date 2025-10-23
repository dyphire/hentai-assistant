#!/usr/bin/env python3
"""
清空 eh_favorites 表数据的脚本
警告：此操作不可逆，请谨慎使用！
"""
import sys
import os

# 添加父目录到路径以便导入模块
sys.path.append('src')

from database import TaskDatabase

def print_statistics(db):
    """打印当前统计信息"""
    conn = db._get_conn()
    cursor = conn.cursor()
    
    # 总记录数
    cursor.execute("SELECT COUNT(*) FROM eh_favorites")
    total = cursor.fetchone()[0]
    
    # 已下载数量
    cursor.execute("SELECT COUNT(*) FROM eh_favorites WHERE downloaded = 1")
    downloaded = cursor.fetchone()[0]
    
    # 有 Komga ID 的数量
    cursor.execute("SELECT COUNT(*) FROM eh_favorites WHERE komga IS NOT NULL")
    with_komga = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\n当前数据统计：")
    print(f"  总记录数: {total}")
    print(f"  已下载: {downloaded}")
    print(f"  已上传到 Komga: {with_komga}")
    print()
    
    return total

def clear_table(db):
    """清空 eh_favorites 表"""
    try:
        conn = db._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM eh_favorites")
        conn.commit()
        deleted_count = cursor.rowcount
        conn.close()
        
        # 清空缓存
        db._latest_added_cache = None
        
        return deleted_count
    except Exception as e:
        print(f"错误：清空表时发生异常: {e}")
        return -1

def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("E-Hentai 收藏夹数据清空工具")
    print("=" * 60)
    print("\n⚠️  警告：此操作将删除 eh_favorites 表中的所有数据！")
    print("⚠️  此操作不可逆，请确保您真的要执行此操作！")
    
    # 检查数据库文件
    db_path = './data/tasks.db'
    if not os.path.exists(db_path):
        print(f"\n错误: 数据库文件不存在: {db_path}")
        return
    
    # 初始化数据库
    db = TaskDatabase(db_path)
    
    # 显示当前数据统计
    total_count = print_statistics(db)
    
    if total_count == 0:
        print("表中没有数据，无需清空。")
        return
    
    # 第一次确认
    print(f"您即将删除 {total_count} 条记录。")
    confirm1 = input("\n确定要继续吗？(yes/no): ").strip().lower()
    
    if confirm1 != 'yes':
        print("\n操作已取消。")
        return
    
    # 第二次确认（需要输入特定文本）
    print("\n⚠️  最后确认：请输入 'DELETE ALL' 来确认删除所有数据")
    confirm2 = input("请输入: ").strip()
    
    if confirm2 != 'DELETE ALL':
        print("\n操作已取消。")
        return
    
    # 执行清空操作
    print("\n正在清空数据...")
    deleted_count = clear_table(db)
    
    if deleted_count >= 0:
        print(f"✓ 成功删除 {deleted_count} 条记录")
        print("\neh_favorites 表已清空。")
        
        # 显示清空后的统计
        print_statistics(db)
    else:
        print("✗ 清空操作失败")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已被用户中断。")
        sys.exit(0)