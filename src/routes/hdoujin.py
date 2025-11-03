"""
HDoujin 相关路由
这个模块包含所有与 HDoujin 相关的 API 路由
使用 Flask Blueprint 实现
"""
from flask import Blueprint, request, current_app
from utils import json_response

# 创建 Blueprint 实例
bp = Blueprint('hdoujin', __name__)

@bp.route('/api/hdoujin/refresh', methods=['POST'])
def refresh_hdoujin_token():
    """
    更新 HDoujin token 配置
    从前端接收新的 clearance、refresh_token 和 user_agent，并更新配置
    """
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块
        from config import load_config, save_config
        import providers.hdoujin as hdoujin

        data = request.get_json()
        if not data:
            return json_response({'error': 'No JSON data provided'}), 400

        clearance = data.get('clearance')
        refresh_token = data.get('refresh_token')
        user_agent = data.get('user_agent')

        if not clearance and not refresh_token and not user_agent:
            return json_response({'error': 'No clearance, refresh_token or user_agent provided'}), 400

        # 更新配置
        config_data = load_config()
        hdoujin_config = config_data.get('hdoujin', {})

        updated = False
        if clearance and clearance != hdoujin_config.get('clearance_token'):
            hdoujin_config['clearance_token'] = clearance
            updated = True

        if refresh_token and refresh_token != hdoujin_config.get('refresh_token'):
            hdoujin_config['refresh_token'] = refresh_token
            updated = True

        if user_agent and user_agent != hdoujin_config.get('user_agent'):
            hdoujin_config['user_agent'] = user_agent
            updated = True

        if updated:
            config_data['hdoujin'] = hdoujin_config
            save_config(config_data)

            # 重新初始化 HDoujin 工具
            hd = hdoujin.HDoujinTools(
                session_token=hdoujin_config.get('session_token', ''),
                refresh_token=hdoujin_config.get('refresh_token', ''),
                clearance_token=hdoujin_config.get('clearance_token', ''),
                user_agent=hdoujin_config.get('user_agent', ''),
                logger=global_logger
            )
            current_app.config['HD_TOOLS'] = hd

            # 验证更新后的 token
            hd_toggle = hd.is_valid_cookie()
            current_app.config['HD_TOGGLE'] = hd_toggle

            if global_logger:
                global_logger.info("成功更新 HDoujin tokens 和 User-Agent")
            return json_response({
                'success': True,
                'message': '成功更新 HDoujin tokens 和 User-Agent',
                'hd_valid': hd_toggle
            }), 200
        else:
            return json_response({
                'success': False,
                'message': '未检测到 tokens 或 User-Agent 的变化'
            }), 200

    except Exception as e:
        if global_logger:
            global_logger.error(f"更新 HDoujin Token 时发生错误: {e}")
        return json_response({
            'error': f'更新 Token 时发生错误: {str(e)}'
        }), 500
