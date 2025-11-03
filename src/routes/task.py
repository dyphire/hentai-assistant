"""
Task 相关路由
这个模块包含所有与任务管理相关的 API 路由
使用 Flask Blueprint 实现
"""
from flask import Blueprint, current_app, request
import sqlite3
from utils import json_response

# 创建 Blueprint 实例
bp = Blueprint('task', __name__)

@bp.route('/api/tasks/stats', methods=['GET'])
def get_task_stats():
    """获取任务统计信息"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入 TaskStatus 枚举
        from utils import TaskStatus

        with sqlite3.connect('./data/tasks.db') as conn:
            conn.row_factory = sqlite3.Row
            # 获取各种状态的任务数量
            cursor = conn.execute('''
                SELECT
                    status,
                    COUNT(*) as count
                FROM tasks
                GROUP BY status
            ''')
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            # 获取总任务数
            cursor = conn.execute('SELECT COUNT(*) as total FROM tasks')
            total_tasks = cursor.fetchone()['total']

            # 获取进行中任务数
            in_progress = status_counts.get(TaskStatus.IN_PROGRESS, 0)

            # 获取已完成任务数
            completed = status_counts.get(TaskStatus.COMPLETED, 0)

            # 获取取消任务数
            cancelled = status_counts.get(TaskStatus.CANCELLED, 0)

            # 获取失败任务数（只包括错误）
            failed = status_counts.get(TaskStatus.ERROR, 0)

            return json_response({
                'total': total_tasks,
                'in_progress': in_progress,
                'completed': completed,
                'cancelled': cancelled,
                'failed': failed,
                'status_counts': status_counts
            })

    except sqlite3.Error as e:
        if global_logger:
            global_logger.error(f"Database error getting task stats: {e}")
        return json_response({'error': 'Failed to get task statistics'}), 500

@bp.route('/api/tasks/clear', methods=['POST'])
def clear_tasks():
    """清理指定状态的任务"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        status_to_clear = request.args.get('status')
        if not status_to_clear:
            return json_response({'error': 'No status provided to clear'}), 400

        # 导入必要的模块和变量
        from database import task_db
        from utils import TaskStatus

        # 从 current_app.config 获取 tasks 和 tasks_lock
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')

        if not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500

        # 从数据库清除任务
        success = task_db.clear_tasks(status_to_clear)
        if not success:
            return json_response({'error': 'Failed to clear tasks from database'}), 500

        # 同时从内存清除对应任务
        with tasks_lock:
            tasks_to_keep = {}
            for tid, task_info in tasks.items():
                should_clear = False

                if status_to_clear == "all_except_in_progress":
                    # 清除除了进行中任务外的所有任务
                    should_clear = task_info.status != TaskStatus.IN_PROGRESS
                elif status_to_clear == "failed":
                    # 清除失败状态的任务（对应数据库中的"错误"状态）
                    should_clear = task_info.status == TaskStatus.ERROR
                elif status_to_clear == "completed":
                    # 清除已完成的任务
                    should_clear = task_info.status == TaskStatus.COMPLETED
                elif status_to_clear == "cancelled":
                    # 清除取消的任务
                    should_clear = task_info.status == TaskStatus.CANCELLED
                elif status_to_clear == "in-progress":
                    # 清除进行中的任务
                    should_clear = task_info.status == TaskStatus.IN_PROGRESS
                else:
                    # 直接状态匹配
                    should_clear = task_info.status == status_to_clear

                if should_clear:
                    # 清除日志缓冲区
                    if hasattr(task_info, 'log_buffer'):
                        task_info.log_buffer.close()
                else:
                    tasks_to_keep[tid] = task_info

            tasks.clear()
            tasks.update(tasks_to_keep)

        return json_response({'message': f'Tasks with status "{status_to_clear}" cleared successfully'}), 200

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error clearing tasks: {e}")
        return json_response({'error': f'Failed to clear tasks: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>')
def get_task(task_id):
    """获取指定任务的完整信息（双数据源查询：内存 -> 数据库）"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块和变量
        from database import task_db

        # 从 current_app.config 获取 tasks 和 tasks_lock
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')

        if not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500

        # 首先检查内存中的任务
        with tasks_lock:
            memory_task = tasks.get(task_id)
            if memory_task:
                task_data = {
                    'id': task_id,
                    'status': memory_task.status,
                    'error': memory_task.error,
                    'filename': memory_task.filename,
                    'progress': memory_task.progress,
                    'downloaded': memory_task.downloaded,
                    'total_size': memory_task.total_size,
                    'speed': memory_task.speed,
                    'log': memory_task.log_buffer.getvalue()
                }
                return json_response(task_data)

        # 如果内存中没有，检查数据库
        db_task = task_db.get_task(task_id)
        if db_task:
            return json_response(db_task)

        return json_response({'error': 'Task not found'}), 404

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error getting task {task_id}: {e}")
        return json_response({'error': f'Failed to get task: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """取消/停止指定任务"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块和变量
        from utils import TaskStatus
        from database import task_db

        # 从 current_app.config 获取 tasks 和 tasks_lock
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')

        if not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500

        with tasks_lock:
            task = tasks.get(task_id)
        if not task:
            return json_response({'error': 'Task not found'}), 404

        # 设置取消标志
        task.cancelled = True

        cancelled = task.future.cancel()
        if cancelled:
            with tasks_lock:
                task.status = TaskStatus.CANCELLED
            # 更新数据库状态
            task_db.update_task(task_id, status=TaskStatus.CANCELLED)
            if global_logger:
                global_logger.info(f"Task {task_id} cancelled successfully")
            return json_response({'message': 'Task cancelled'})
        else:
            return json_response({'message': 'Task could not be cancelled (可能已在运行或已完成)'}), 200

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error stopping task {task_id}: {e}")
        return json_response({'error': f'Failed to stop task: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/retry', methods=['POST'])
def retry_task(task_id):
    """重试失败的任务"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块和变量
        from utils import TaskStatus
        from database import task_db
        from datetime import datetime, timezone
        import sqlite3
        import main

        # 从 current_app.config 获取 tasks、tasks_lock 和 executor
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')
        executor = current_app.config.get('EXECUTOR')

        if not tasks_lock or not executor:
            return json_response({'error': 'Server not properly initialized'}), 500

        # 从数据库获取任务信息
        task_info = task_db.get_task(task_id)
        if not task_info:
            return json_response({'error': 'Task not found'}), 404

        # 检查任务状态是否为失败
        if task_info['status'] != TaskStatus.ERROR:
            return json_response({'error': 'Only failed tasks can be retried'}), 400

        # 检查是否有URL信息
        if not task_info.get('url'):
            return json_response({'error': 'Task URL information is missing, cannot retry'}), 400

        # 获取URL和mode
        url = task_info['url']
        mode = task_info.get('mode')

        # 创建新的任务ID
        new_task_id = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S%f')

        # 添加新任务到数据库
        task_db.add_task(new_task_id, status=TaskStatus.IN_PROGRESS, url=url, mode=mode)

        # 删除原来的失败任务
        try:
            with sqlite3.connect('./data/tasks.db') as conn:
                conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
                conn.commit()
            if global_logger:
                global_logger.info(f"已从数据库删除失败任务 {task_id}")
        except sqlite3.Error as e:
            if global_logger:
                global_logger.error(f"删除失败任务时发生数据库错误: {e}")

        # 从内存中删除原来的失败任务
        with tasks_lock:
            if task_id in tasks:
                # 关闭日志缓冲区
                if hasattr(tasks[task_id], 'log_buffer'):
                    tasks[task_id].log_buffer.close()
                del tasks[task_id]

        # 创建新的任务执行
        logger, log_buffer = main.get_task_logger(new_task_id)
        future = executor.submit(main.download_gallery_task, url, mode, new_task_id, logger)

        # 更新内存中的任务信息
        with tasks_lock:
            tasks[new_task_id] = main.TaskInfo(future, logger, log_buffer)

        if global_logger:
            global_logger.info(f"Task retry started with new ID {new_task_id}")
        return json_response({'message': f'Task retry started with new ID {new_task_id}', 'task_id': new_task_id}), 202

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error retrying task {task_id}: {e}")
        return json_response({'error': f'Failed to retry task: {str(e)}'}), 500

@bp.route('/api/tasks', methods=['GET'])
def get_tasks():
    """获取任务列表（支持分页和状态过滤）"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块和变量
        from database import task_db
        from utils import TaskStatus
        import sqlite3

        # 从 current_app.config 获取 tasks 和 tasks_lock
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')

        if not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500

        status_filter = request.args.get('status')
        
        # 安全的参数转换，添加验证
        try:
            page = int(request.args.get('page', 1))
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            page = 1
        
        try:
            page_size = int(request.args.get('page_size', 20))
            if page_size < 1:
                page_size = 20
            elif page_size > 100:  # 限制最大页面大小
                page_size = 100
        except (ValueError, TypeError):
            page_size = 20

        # 从数据库获取任务列表
        db_tasks, total = task_db.get_tasks(status_filter, page, page_size)

        # 合并内存中的活跃任务信息
        with tasks_lock:
            for db_task in db_tasks:
                task_id = db_task['id']
                if task_id in tasks:
                    memory_task = tasks[task_id]
                    # 用内存中的最新信息更新数据库任务
                    db_task.update({
                        'status': memory_task.status,
                        'error': memory_task.error,
                        'log': memory_task.log_buffer.getvalue(),
                        'filename': memory_task.filename,
                        'progress': memory_task.progress,
                        'downloaded': memory_task.downloaded,
                        'total_size': memory_task.total_size,
                        'speed': memory_task.speed
                    })

                    # 同步更新数据库
                    task_db.update_task(
                        task_id,
                        status=memory_task.status,
                        error=memory_task.error,
                        log=memory_task.log_buffer.getvalue(),
                        filename=memory_task.filename,
                        progress=memory_task.progress,
                        downloaded=memory_task.downloaded,
                        total_size=memory_task.total_size,
                        speed=memory_task.speed
                    )

        # 按任务ID降序排序（任务ID基于时间，新的ID更大）
        db_tasks.sort(key=lambda x: x.get('id', ''), reverse=True)

        # 获取各个状态的任务数量统计
        try:
            with sqlite3.connect('./data/tasks.db') as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT
                        status,
                        COUNT(*) as count
                    FROM tasks
                    GROUP BY status
                ''')
                status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

                # 获取各个状态的总数
                all_count = sum(status_counts.values())
                in_progress_count = status_counts.get(TaskStatus.IN_PROGRESS, 0)
                completed_count = status_counts.get(TaskStatus.COMPLETED, 0)
                cancelled_count = status_counts.get(TaskStatus.CANCELLED, 0)
                failed_count = status_counts.get(TaskStatus.ERROR, 0)
        except sqlite3.Error as e:
            if global_logger:
                global_logger.error(f"Database error getting status counts: {e}")
            all_count = total
            in_progress_count = 0
            completed_count = 0
            cancelled_count = 0
            failed_count = 0

        return json_response({
            'tasks': db_tasks,
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'status_counts': {
                'all': all_count,
                'in-progress': in_progress_count,
                'completed': completed_count,
                'cancelled': cancelled_count,
                'failed': failed_count
            }
        })

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error getting tasks: {e}")
        return json_response({'error': f'Failed to get tasks: {str(e)}'}), 500
