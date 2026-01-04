"""
Download 相关路由
这个模块包含所有与下载任务相关的 API 路由
使用 Flask Blueprint 实现
"""
from flask import Blueprint, request, current_app
from datetime import datetime, timezone
from utils import json_response

# 创建 Blueprint 实例
bp = Blueprint('download', __name__)

@bp.route('/api/download', methods=['GET'])
def download_url():
    """
    创建下载任务
    
    参数:
        url: 画廊 URL（必需）
        mode: 下载模式（可选，如 'torrent', 'archive'）
        fav: 收藏夹标志（可选）
            - true/t/1/y/yes: 添加到收藏夹 0
            - 0-9: 添加到指定收藏夹
            - false/其他: 不添加到收藏夹
    
    返回:
        200: 任务已存在（已完成或进行中）
        202: 任务已创建或重试
        400: 参数错误
        500: 服务器错误
    """
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        url = request.args.get('url')
        mode = request.args.get('mode')
        fav_param = request.args.get('fav', 'false').lower()
        
        # 新的 fav 参数处理逻辑
        # 如果是 true, t, 1, y, yes -> '0'
        # 如果是数字 0-9 -> 该数字的字符串
        # 否则 -> False
        if fav_param in ('true', 't', '1', 'y', 'yes'):
            favcat = '0'
        elif fav_param.isdigit() and 0 <= int(fav_param) <= 9:
            favcat = fav_param
        else:
            favcat = False

        if not url:
            return json_response({'error': 'No URL provided'}), 400
        
        # 从 current_app.config 获取共享对象
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')
        executor = current_app.config.get('EXECUTOR')
        
        if not executor or not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500
        
        # 导入必要的模块
        from database import task_db
        from utils import TaskStatus
        import sqlite3
        
        # 规范化 URL 并检查重复任务
        try:
            normalized_url, _ = task_db.normalize_url(url)
            existing_task = task_db.get_task_by_normalized_url(normalized_url)
            
            if existing_task:
                existing_status = existing_task['status']
                existing_task_id = existing_task['id']
                
                # 已完成或进行中的任务 -> 跳过
                if existing_status in (TaskStatus.COMPLETED, TaskStatus.IN_PROGRESS):
                    if global_logger:
                        global_logger.info(f"Task for URL {url} already exists with status {existing_status}, task_id: {existing_task_id}")
                    
                    return json_response({
                        'message': 'Task already exists',
                        'task_id': existing_task_id,
                        'status': existing_status,
                        'reason': 'already_completed' if existing_status == TaskStatus.COMPLETED else 'in_progress',
                        'url': url
                    }), 200
                
                # 失败或取消的任务 -> 重试
                elif existing_status in (TaskStatus.ERROR, TaskStatus.CANCELLED):
                    if global_logger:
                        global_logger.info(f"Task for URL {url} has status {existing_status}, retrying with new task ID")
                    
                    # 删除旧任务（数据库）
                    try:
                        with sqlite3.connect('./data/tasks.db') as conn:
                            conn.execute('DELETE FROM tasks WHERE id = ?', (existing_task_id,))
                            conn.commit()
                        if global_logger:
                            global_logger.info(f"已从数据库删除任务 {existing_task_id}")
                    except sqlite3.Error as e:
                        if global_logger:
                            global_logger.error(f"删除旧任务时发生数据库错误: {e}")
                    
                    # 从内存中删除旧任务
                    with tasks_lock:
                        if existing_task_id in tasks:
                            if hasattr(tasks[existing_task_id], 'log_buffer'):
                                tasks[existing_task_id].log_buffer.close()
                            del tasks[existing_task_id]
                    
                    # 使用原任务的参数（如果当前请求没有提供）
                    if not mode and existing_task.get('mode'):
                        mode = existing_task['mode']
                    if favcat is False and existing_task.get('favcat'):
                        favcat = existing_task['favcat']
                    
                    # 继续创建新任务（下面的代码会处理）
                    # 记录这是一次重试
                    is_retry = True
                    previous_task_id = existing_task_id
                else:
                    # 其他状态，正常创建新任务
                    is_retry = False
                    previous_task_id = None
            else:
                # 没有重复任务
                is_retry = False
                previous_task_id = None
        except Exception as e:
            # 如果规范化或查询失败，继续正常流程
            if global_logger:
                global_logger.warning(f"Error checking for duplicate task: {e}")
            is_retry = False
            previous_task_id = None
        
        # 创建新任务
        # 两位年份+月日时分秒，使用UTC时间避免时区问题
        task_id = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S%f')
        
        # 从 current_app.config 获取函数和类
        get_task_logger = current_app.config.get('GET_TASK_LOGGER')
        task_failure_processing = current_app.config.get('TASK_FAILURE_PROCESSING')
        download_gallery_task = current_app.config.get('DOWNLOAD_GALLERY_TASK')
        TaskInfo = current_app.config.get('TASK_INFO_CLASS')
        
        if not all([get_task_logger, task_failure_processing, download_gallery_task, TaskInfo]):
            return json_response({'error': 'Server functions not properly initialized'}), 500
        
        logger, log_buffer = get_task_logger(task_id)
        
        # 动态应用装饰器
        decorated_download_task = task_failure_processing(url, task_id, logger, tasks, tasks_lock)(download_gallery_task)
        
        future = executor.submit(decorated_download_task, url, mode, task_id, logger, favcat, tasks, tasks_lock)
        with tasks_lock:
            tasks[task_id] = TaskInfo(future, logger, log_buffer)

        # 添加任务到数据库，包含URL、mode和favcat信息用于重试
        # 将 favcat 转换为字符串存储（False -> None）
        favcat_to_save = str(favcat) if favcat is not False else None
        task_db.add_task(task_id, status=TaskStatus.IN_PROGRESS, url=url, mode=mode, favcat=favcat_to_save)

        # 根据是否是重试返回不同的消息
        if is_retry:
            return json_response({
                'message': f'Previous task {existing_status}, retrying with new task ID {task_id}',
                'task_id': task_id,
                'previous_task_id': previous_task_id,
                'retried': True
            }), 202
        else:
            return json_response({
                'message': f"Download task for {url} started with task ID {task_id}.",
                'task_id': task_id
            }), 202

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error creating download task: {e}")
        return json_response({'error': f'Failed to create download task: {str(e)}'}), 500