"""
调度器管理路由
提供查看和管理计划任务的 API
"""
from flask import Blueprint, current_app
from utils import json_response
from scheduler import scheduler

bp = Blueprint('scheduler', __name__)

@bp.route('/api/scheduler/jobs', methods=['GET'])
def get_scheduler_jobs():
    """
    获取所有计划任务的状态信息
    
    返回格式:
    {
        "jobs": [
            {
                "id": "任务ID",
                "name": "任务名称",
                "trigger": "触发器类型",
                "interval": "执行间隔",
                "next_run_time": "下次运行时间",
                "enabled": true/false
            }
        ],
        "scheduler_running": true/false,
        "total_jobs": 5
    }
    """
    try:
        jobs_info = []
        
        for job in scheduler.get_jobs():
            job_data = {
                'id': job.id,
                'name': job.func.__name__,
                'trigger': str(job.trigger),
                'next_run_time': job.next_run_time.isoformat() if job.next_run_time else None,
                'enabled': True
            }
            
            # 解析触发器信息以获取间隔
            trigger_str = str(job.trigger)
            if 'interval' in trigger_str:
                # 提取间隔信息，例如 "interval[6:00:00]" 或 "interval[1 day, 0:00:00]"
                import re
                match = re.search(r'interval\[(.*?)\]', trigger_str)
                if match:
                    job_data['interval'] = match.group(1)
            
            jobs_info.append(job_data)
        
        # 按任务 ID 排序
        jobs_info.sort(key=lambda x: x['id'])
        
        return json_response({
            'scheduler_running': scheduler.running,
            'total_jobs': len(jobs_info),
            'jobs': jobs_info
        })
    
    except Exception as e:
        current_app.logger.error(f"获取调度器任务列表失败: {e}", exc_info=True)
        return json_response({'error': f'获取任务列表失败: {str(e)}'}), 500
