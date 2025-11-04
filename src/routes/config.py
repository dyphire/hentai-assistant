"""
配置管理路由
这个模块包含所有与配置管理相关的 API 路由
使用 Flask Blueprint 实现
"""
from flask import Blueprint, request, current_app
from utils import json_response

# 创建 Blueprint 实例
bp = Blueprint('config', __name__)

@bp.route('/api/config', methods=['GET'])
def get_config():
    """获取应用配置"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块
        from config import load_config

        config_data = load_config()

        # 添加状态信息
        config_data['status'] = {
            'eh_valid': current_app.config.get('EH_VALID', False),
            'exh_valid': current_app.config.get('EXH_VALID', False),
            'nh_toggle': current_app.config.get('NH_TOGGLE', False),
            'hd_toggle': current_app.config.get('HD_TOGGLE', False),
            'aria2_toggle': current_app.config.get('ARIA2_TOGGLE', False),
            'komga_toggle': current_app.config.get('KOMGA_TOGGLE', False),
            'notification_toggle': current_app.config.get('NOTIFICATION', {}).get('enable', False),
            'eh_funds': current_app.config.get('EH_FUNDS', {'GP': '-', 'Credits': '-'})
        }

        # 检查是否有外部通知器配置（除了 komga 自己）
        notification_config = current_app.config.get('NOTIFICATION', {})
        has_external_notifier = any(
            name != 'komga' and details.get('enable', False)
            for name, details in notification_config.items()
            if isinstance(details, dict)
        )

        # 添加通知子进程信息（从 app.config 读取）
        try:
            # 直接从 app.config 读取 notification 进程状态
            notification_process = current_app.config.get('NOTIFICATION_PROCESS')
            notification_pid = current_app.config.get('NOTIFICATION_PROCESS_PID')

            # 获取当前进程状态（始终检查，不管komga是否启用）
            notification_running = notification_process and notification_process.poll() is None

            # 判断 notification 应该启动的条件（komga 启用且有外部通知器）
            should_start_notification = config_data['status']['komga_toggle'] and has_external_notifier

            # 如果notification进程正在运行且应该启动，报告运行状态
            if notification_running and should_start_notification:
                config_data['status']['notification_pid'] = notification_pid
                config_data['status']['notification_status'] = 'running'
            elif should_start_notification:
                # 应该启动但没启动 → 异常
                config_data['status']['notification_pid'] = None
                config_data['status']['notification_status'] = 'error'
            else:
                # 不需要启动 → 未启动
                config_data['status']['notification_pid'] = None
                config_data['status']['notification_status'] = 'not_started'

        except Exception as e:
            if global_logger:
                global_logger.error(f"Failed to get notification process info: {e}")
            config_data['status']['notification_pid'] = None
            config_data['status']['notification_status'] = 'error'

        return json_response(config_data)

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error getting config: {e}")
        return json_response({'error': f'Failed to get config: {str(e)}'}), 500

@bp.route('/api/config', methods=['POST'])
def update_config():
    """更新应用配置"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块
        from config import save_config
        import main

        data = request.get_json()
        source = request.args.get('source')

        if not data:
            return json_response({'error': 'Invalid JSON data'}), 400

        try:
            save_config(data)
        except Exception as e:
            return json_response({'error': f'Failed to save config: {e}'}), 500

        if source == 'notification':
            # 只更新通知相关的配置，不触发完整的 check_config
            notification_config = data.get('notification', {})
            is_any_notifier_enabled = any(
                details.get('enable') for name, details in notification_config.items()
            )
            notification_config['enable'] = is_any_notifier_enabled
            current_app.config['NOTIFICATION'] = notification_config

            if global_logger:
                global_logger.info("Notification config updated without triggering a full service check.")

            # 可能需要重启通知子进程以应用更改
            if current_app.config.get('KOMGA_TOGGLE'):
                if global_logger:
                    global_logger.info("Restarting notification listener to apply changes...")
                app_ref = current_app._get_current_object()  # type: ignore
                main.stop_notification_process(app_ref)
                main.start_notification_process(app_ref)

            return json_response({'message': 'Notification config updated successfully'}), 200
        else:
            # 原始的完整更新流程
            current_app.config['CHECKING_CONFIG'] = True
            # 保存当前 app 引用，在后台线程中使用应用上下文
            app_ref = current_app._get_current_object()  # type: ignore
            def run_check_config():
                with app_ref.app_context():
                    main.check_config(app_ref)
            main.executor.submit(run_check_config)
            return json_response({'message': 'Config updated successfully', 'status_check_started': True}), 200

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error updating config: {e}")
        return json_response({'error': f'Failed to update config: {str(e)}'}), 500
