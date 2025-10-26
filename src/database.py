import sqlite3
import threading
import os
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from utils import TaskStatus, parse_gallery_url, check_dirs

class TaskDatabase:
    STATUS_MAP = {
        "in-progress": TaskStatus.IN_PROGRESS,
        "completed": TaskStatus.COMPLETED,
        "cancelled": TaskStatus.CANCELLED,
        "failed": TaskStatus.ERROR,
    }

    def __init__(self, db_path: str = './data/tasks.db'):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._latest_added_cache = None  # 缓存最新的收藏时间
        
        # 确保数据库文件的父目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            check_dirs(db_dir)
        
        self._init_database()

    def _get_conn(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)

    def _init_database(self):
        """初始化数据库表"""
        with self._get_conn() as conn:
            # 先创建表（如果不存在）
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    error TEXT,
                    log TEXT,
                    filename TEXT,
                    progress INTEGER DEFAULT 0,
                    downloaded INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    speed INTEGER DEFAULT 0,
                    url TEXT,
                    mode TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建 global 表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS global (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # 检查已存在表的字段
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]

            # 如果表已存在但缺少新字段，添加它们
            for col in ("url", "mode"):
                if col not in columns:
                    conn.execute(f'ALTER TABLE tasks ADD COLUMN {col} TEXT')

            conn.commit()

            # 创建 eh_favorites 表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS eh_favorites (
                    gid INTEGER PRIMARY KEY,
                    token TEXT NOT NULL,
                    title TEXT,
                    originaltitle TEXT,
                    favcat INTEGER,
                    downloaded BOOLEAN DEFAULT 0,
                    komga TEXT,
                    added TEXT
                )
            ''')

            # 检查 eh_favorites 表的字段
            cursor = conn.execute("PRAGMA table_info(eh_favorites)")
            columns = [row[1] for row in cursor.fetchall()]

            # 如果表已存在但缺少新字段，添加它们
            if 'added' not in columns:
                conn.execute('ALTER TABLE eh_favorites ADD COLUMN added TEXT')
            if 'originaltitle' not in columns:
                conn.execute('ALTER TABLE eh_favorites ADD COLUMN originaltitle TEXT')

            conn.commit()

    def add_task(self, task_id: str, status: str = TaskStatus.IN_PROGRESS,
                 filename: Optional[str] = None, error: Optional[str] = None,
                 url: Optional[str] = None, mode: Optional[str] = None) -> bool:
        """添加新任务"""
        status = self.STATUS_MAP.get(status, status)
        with self.lock:
            try:
                with self._get_conn() as conn:
                    now = datetime.now(timezone.utc).isoformat()
                    conn.execute('''
                        INSERT OR REPLACE INTO tasks
                        (id, status, filename, error, url, mode, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (task_id, status, filename, error, url, mode, now, now))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error adding task: {e}")
                return False

    def update_task(self, task_id: str, status: Optional[str] = None, error: Optional[str] = None,
                    log: Optional[str] = None, filename: Optional[str] = None, progress: Optional[int] = None,
                    downloaded: Optional[int] = None, total_size: Optional[int] = None, speed: Optional[int] = None,
                    url: Optional[str] = None, mode: Optional[str] = None) -> bool:
        """更新任务信息"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    updates = []
                    params = []

                    if status is not None:
                        updates.append("status = ?")
                        params.append(self.STATUS_MAP.get(status, status))
                    if error is not None:
                        updates.append("error = ?")
                        params.append(error)
                    if log is not None:
                        updates.append("log = ?")
                        params.append(log)
                    if filename is not None:
                        updates.append("filename = ?")
                        params.append(filename)
                    if progress is not None:
                        updates.append("progress = ?")
                        params.append(progress)
                    if downloaded is not None:
                        updates.append("downloaded = ?")
                        params.append(downloaded)
                    if total_size is not None:
                        updates.append("total_size = ?")
                        params.append(total_size)
                    if speed is not None:
                        updates.append("speed = ?")
                        params.append(speed)
                    if url is not None:
                        updates.append("url = ?")
                        params.append(url)
                    if mode is not None:
                        updates.append("mode = ?")
                        params.append(mode)

                    if updates:
                        updates.append("updated_at = ?")
                        params.append(datetime.now(timezone.utc).isoformat())
                        params.append(task_id)

                        query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
                        conn.execute(query, params)
                        conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error updating task: {e}")
                return False

    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取单个任务"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                print(f"Database error getting task: {e}")
                return None

    def get_tasks(self, status_filter: Optional[str] = None, page: int = 1,
                  page_size: int = 20, order_by: str = "created_at DESC") -> Tuple[List[Dict], int]:
        """获取任务列表，支持分页和状态过滤"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row

                    where_clause = ""
                    params = []

                    if status_filter:
                        status_cn = self.STATUS_MAP.get(status_filter, status_filter)
                        where_clause = "WHERE status = ?"
                        params.append(status_cn)

                    # 获取总数
                    count_query = f"SELECT COUNT(*) FROM tasks {where_clause}"
                    cursor = conn.execute(count_query, params)
                    total = cursor.fetchone()[0]

                    # 获取分页数据
                    offset = (page - 1) * page_size
                    data_query = f"""
                        SELECT * FROM tasks {where_clause}
                        ORDER BY {order_by}
                        LIMIT ? OFFSET ?
                    """
                    params.extend([page_size, offset])

                    cursor = conn.execute(data_query, params)
                    tasks = [dict(row) for row in cursor.fetchall()]

                    return tasks, total
            except sqlite3.Error as e:
                print(f"Database error getting tasks: {e}")
                return [], 0

    def clear_tasks(self, status: str) -> bool:
        """清除指定状态的任务"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    if status == 'all_except_in_progress':
                        # 清除除了进行中任务外的所有任务
                        conn.execute('DELETE FROM tasks WHERE status != ?', (TaskStatus.IN_PROGRESS,))
                    else:
                        # 将前端状态映射为数据库状态
                        status_cn = self.STATUS_MAP.get(status, status)
                        conn.execute('DELETE FROM tasks WHERE status = ?', (status_cn,))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error clearing tasks: {e}")
                return False

    def migrate_memory_tasks(self, memory_tasks: Dict) -> bool:
        """将内存中的任务迁移到数据库"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    now = datetime.now(timezone.utc).isoformat()
                    for task_id, task_info in memory_tasks.items():
                        log_content = task_info.log_buffer.getvalue() if hasattr(task_info, 'log_buffer') else ""
                        conn.execute('''
                            INSERT OR REPLACE INTO tasks
                            (id, status, error, log, filename, progress, downloaded,
                             total_size, speed, url, mode, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            task_id,
                            self.STATUS_MAP.get(task_info.status, task_info.status),
                            task_info.error,
                            log_content,
                            task_info.filename,
                            task_info.progress,
                            task_info.downloaded,
                            task_info.total_size,
                            task_info.speed,
                            getattr(task_info, "url", None),
                            getattr(task_info, "mode", None),
                            now,
                            now
                        ))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error migrating tasks: {e}")
                return False


    def set_global_state(self, key: str, value: str) -> bool:
        """设置全局状态值"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.execute('INSERT OR REPLACE INTO global (key, value) VALUES (?, ?)', (key, value))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error setting global state: {e}")
                return False

    def get_global_state(self, key: str) -> Optional[str]:
        """获取全局状态值"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('SELECT value FROM global WHERE key = ?', (key,))
                    row = cursor.fetchone()
                    return row[0] if row else None
            except sqlite3.Error as e:
                print(f"Database error getting global state: {e}")
                return None

    def upsert_eh_favorites(self, favorites: List[Dict]) -> bool:
        """将 E-Hentai 收藏夹数据添加或更新到数据库 (UPSERT)"""
        with self.lock:
            favorites_to_upsert = []
            for fav in favorites:
                gid, token = parse_gallery_url(fav.get('url', ''))
                if gid and token:
                    favorites_to_upsert.append({
                        'gid': gid,
                        'token': token,
                        'originaltitle': fav.get('title'),
                        'favcat': fav.get('favcat'),
                        'added': fav.get('added')
                    })

            if not favorites_to_upsert:
                return True

            try:
                with self._get_conn() as conn:
                    conn.executemany('''
                        INSERT INTO eh_favorites (gid, token, originaltitle, favcat, added)
                        VALUES (:gid, :token, :originaltitle, :favcat, :added)
                        ON CONFLICT(gid) DO UPDATE SET
                            token = excluded.token,
                            originaltitle = excluded.originaltitle,
                            favcat = excluded.favcat,
                            added = excluded.added
                    ''', favorites_to_upsert)
                    conn.commit()
                
                # 更新缓存：找出最新的 added 时间
                added_times = [f['added'] for f in favorites_to_upsert if f.get('added')]
                if added_times:
                    latest = max(added_times)
                    if self._latest_added_cache is None or latest > self._latest_added_cache:
                        self._latest_added_cache = latest
                
                return True
            except sqlite3.Error as e:
                print(f"Database error upserting EH favorites: {e}")
                return False

    def add_eh_favorites(self, favorites: List[Dict]) -> bool:
        """添加 E-Hentai 收藏夹数据到数据库（不更新已存在的记录）"""
        with self.lock:
            favorites_to_add = []
            for fav in favorites:
                gid, token = parse_gallery_url(fav.get('url', ''))
                if gid and token:
                    favorites_to_add.append({
                        'gid': gid,
                        'token': token,
                        'title': fav.get('title'),
                        'originaltitle': fav.get('originaltitle'),
                        'favcat': fav.get('favcat')
                    })

            if not favorites_to_add:
                return True

            try:
                with self._get_conn() as conn:
                    conn.executemany('''
                        INSERT OR IGNORE INTO eh_favorites (gid, token, title, originaltitle, favcat)
                        VALUES (:gid, :token, :title, :originaltitle, :favcat)
                    ''', favorites_to_add)
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error adding EH favorites: {e}")
                return False

    def get_eh_favorites_by_favcat(self, favcat_list: List[str]) -> List[Dict]:
        """根据收藏夹分类ID获取所有画廊"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    placeholders = ','.join('?' for _ in favcat_list)
                    query = f"SELECT gid, token, favcat FROM eh_favorites WHERE favcat IN ({placeholders})"
                    cursor = conn.execute(query, favcat_list)
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                print(f"Database error getting EH favorites by favcat: {e}")
                return []

    def delete_eh_favorites_by_gids(self, gids: List[int]) -> bool:
        """根据 GID 列表删除收藏夹记录"""
        if not gids:
            return True
        with self.lock:
            try:
                with self._get_conn() as conn:
                    placeholders = ','.join('?' for _ in gids)
                    query = f"DELETE FROM eh_favorites WHERE gid IN ({placeholders})"
                    conn.execute(query, gids)
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error deleting EH favorites: {e}")
                return False

    def get_eh_favorite_by_gid(self, gid: int) -> Optional[Dict]:
        """根据 GID 获取单个收藏夹项目"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM eh_favorites WHERE gid = ?', (gid,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                print(f"Database error getting EH favorite by GID: {e}")
                return None

    def get_undownloaded_favorites(self) -> List[Dict]:
        """获取所有尚未下载的收藏夹项目"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM eh_favorites WHERE downloaded = ?', (False,))
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                print(f"Database error getting undownloaded favorites: {e}")
                return []

    def mark_favorite_as_downloaded(self, gid: int) -> bool:
        """将指定 GID 的收藏夹项目标记为已下载"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('UPDATE eh_favorites SET downloaded = ? WHERE gid = ?', (True, gid))
                    conn.commit()
                    return cursor.rowcount > 0
            except sqlite3.Error as e:
                print(f"Database error marking favorite as downloaded: {e}")
                return False

    def update_favorite_komga_id(self, gid: int, komga_id: str, komga_title: str) -> bool:
        """将指定 GID 的收藏夹项目的 Komga ID 记录下来，并标记为已下载，同时将 Komga 中的标题写入 title 字段"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('UPDATE eh_favorites SET komga = ?, downloaded = ?, title = ? WHERE gid = ?', (komga_id, True, komga_title, gid))
                    conn.commit()
                    return cursor.rowcount > 0
            except sqlite3.Error as e:
                print(f"Database error updating favorite's Komga ID: {e}")
                return False

    def update_favorite_favcat(self, gid: int, favcat: str) -> bool:
        """更新指定 GID 的收藏夹项目的 favcat"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('UPDATE eh_favorites SET favcat = ? WHERE gid = ?', (favcat, gid))
                    conn.commit()
                    return cursor.rowcount > 0
            except sqlite3.Error as e:
                print(f"Database error updating favorite's favcat: {e}")
                return False

    def get_favorites_without_komga_id(self) -> List[Dict]:
        """获取所有 komga 字段为空的收藏夹项目"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM eh_favorites WHERE komga IS NULL')
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                print(f"Database error getting favorites without komga id: {e}")
                return []

    def get_favorite_by_komga_id(self, komga_id: str) -> Optional[Dict]:
        """根据 Komga Book ID 获取单个收藏夹项目"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM eh_favorites WHERE komga = ?', (komga_id,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                print(f"Database error getting favorite by Komga ID: {e}")
                return None

    def get_latest_added_time(self) -> Optional[str]:
        """获取最新的收藏时间（带缓存）"""
        # 如果缓存存在，直接返回
        if self._latest_added_cache is not None:
            return self._latest_added_cache
        
        # 缓存为空时查询数据库
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('SELECT MAX(added) FROM eh_favorites')
                    row = cursor.fetchone()
                    self._latest_added_cache = row[0] if row and row[0] else None
                    return self._latest_added_cache
            except sqlite3.Error as e:
                print(f"Database error getting latest added time: {e}")
                return None

# 全局数据库实例
task_db = TaskDatabase()
