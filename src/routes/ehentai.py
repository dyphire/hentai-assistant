"""
E-Hentai 相关路由
这个模块包含所有与 E-Hentai 相关的 API 路由
使用 Flask Blueprint 实现
"""
from flask import Blueprint, request, current_app
from logging import Logger
from utils import json_response

# 创建 Blueprint 实例
bp = Blueprint('ehentai', __name__)

def update_eh_funds(eh_funds):
    """更新资金信息到 app.config 和数据库"""
    import main
    main.update_eh_funds(eh_funds)


@bp.route('/api/ehentai/favorites/categories', methods=['GET'])
def get_ehentai_favcats():
    """获取 E-Hentai 收藏夹分类列表"""
    if 'EH_TOOLS' in current_app.config:
        eh_tools = current_app.config['EH_TOOLS']
        favcat_list = eh_tools.get_favcat_list()

        if not favcat_list and current_app.config.get('EH_FAV_SYNC_ENABLED'):
             return json_response({'message': '正在获取收藏夹列表, 请刷新页面重试。'}), 202

        return json_response(favcat_list)
    else:
        return json_response({'error': 'E-Hentai tools not initialized'}), 500

@bp.route('/api/ehentai/favorites/sync', methods=['GET'])
def trigger_sync_favorites():
    """
    从线上同步 E-Hentai 收藏夹到本地数据库
    参数: download=true/false (可选，是否同步后自动下载)
    """
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        if not current_app.config.get('EH_FAV_SYNC_ENABLED'):
            return json_response({'error': 'E-Hentai 收藏夹同步功能未启用'}), 400

        # 获取 download 参数
        download_param = request.args.get('download', '').lower()
        if download_param in ('true', 't', '1', 'y', 'yes'):
            auto_download = True
        elif download_param in ('false', 'f', '0', 'n', 'no'):
            auto_download = False
        else:
            # 未指定则使用 None，让 sync_eh_favorites_job 使用配置值
            auto_download = None

        from scheduler import sync_eh_favorites_job
        from concurrent.futures import ThreadPoolExecutor
        executor = ThreadPoolExecutor(max_workers=5)
        executor.submit(sync_eh_favorites_job, auto_download)

        download_status = auto_download if auto_download is not None else current_app.config.get('EH_FAV_AUTO_DOWNLOAD', False)
        if global_logger:
            global_logger.info(f"手动触发 E-Hentai 收藏夹同步任务 (自动下载: {download_status})")
        return json_response({
            'message': 'E-Hentai 收藏夹同步任务已启动',
            'auto_download': download_status
        }), 202

    except Exception as e:
        if global_logger:
            global_logger.error(f"触发 E-Hentai 收藏夹同步任务失败: {e}")
        return json_response({'error': f'触发同步任务失败: {str(e)}'}), 500

@bp.route('/api/ehentai/refresh', methods=['GET'])
def refresh_ehentai_cookie():
    """
    验证 E-Hentai cookie 的有效性并更新资金信息
    返回验证状态、资金信息以及更新的 sk 和 igneous cookie
    """
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        ehentai_tool = current_app.config.get('EH_TOOLS')
        if not ehentai_tool:
            if global_logger:
                global_logger.warning("EH_TOOLS 未初始化，无法验证 Cookie")
            return json_response({
                'error': 'E-Hentai tools not initialized'
            }), 500

        # 验证 cookie
        eh_valid, exh_valid, eh_funds = ehentai_tool.is_valid_cookie()

        # 更新 E-Hentai 和 ExHentai 验证状态
        current_app.config['EH_VALID'] = eh_valid
        current_app.config['EXH_VALID'] = exh_valid

        # 获取更新后的临时 cookies
        cached_cookies = ehentai_tool.get_cached_cookies()

        if eh_valid or exh_valid:
            # 更新资金信息
            update_eh_funds(eh_funds)
            if global_logger:
                global_logger.info(f"E-Hentai Cookie 验证成功 (EH: {eh_valid}, ExH: {exh_valid})")

            return json_response({
                'status': 'success',
                'eh_valid': eh_valid,
                'exh_valid': exh_valid,
                'funds': eh_funds,
                'sk': cached_cookies.get('sk'),
                'igneous': cached_cookies.get('igneous'),
                'message': 'Cookie 验证成功'
            }), 200
        else:
            if global_logger:
                global_logger.warning("E-Hentai Cookie 验证失败")
            return json_response({
                'status': 'failed',
                'eh_valid': False,
                'exh_valid': False,
                'funds': {'GP': '-', 'Credits': '-'},
                'sk': None,
                'igneous': None,
                'message': 'Cookie 验证失败，请检查配置'
            }), 200

    except Exception as e:
        if global_logger:
            global_logger.error(f"验证 E-Hentai Cookie 时发生错误: {e}")
        return json_response({
            'error': f'验证 Cookie 时发生错误: {str(e)}'
        }), 500

@bp.route('/api/ehentai/test_status', methods=['POST'])
def test_ehentai_status():
    """
    测试接口：临时设置 E-Hentai 状态用于前端测试
    参数: eh_valid (bool), exh_valid (bool)
    例如: POST /api/ehentai/test_status?eh_valid=false&exh_valid=false
    """
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        eh_valid_param = request.args.get('eh_valid', '').lower()
        exh_valid_param = request.args.get('exh_valid', '').lower()

        # 解析布尔值
        def parse_bool(value):
            if value in ('true', 't', '1', 'y', 'yes'):
                return True
            elif value in ('false', 'f', '0', 'n', 'no'):
                return False
            elif value in ('null', 'none', ''):
                return None
            return None

        eh_valid = parse_bool(eh_valid_param)
        exh_valid = parse_bool(exh_valid_param)

        # 更新状态
        current_app.config['EH_VALID'] = eh_valid
        current_app.config['EXH_VALID'] = exh_valid

        if global_logger:
            global_logger.info(f"测试模式：设置 E-Hentai 状态为 EH_VALID={eh_valid}, EXH_VALID={exh_valid}")

        return json_response({
            'message': '测试状态已设置',
            'eh_valid': eh_valid,
            'exh_valid': exh_valid,
            'status_text': '正常' if exh_valid else ('异常' if (eh_valid is None and exh_valid is None) else '受限')
        }), 200

    except Exception as e:
        if global_logger:
            global_logger.error(f"设置测试状态失败: {e}")
        return json_response({'error': f'设置测试状态失败: {str(e)}'}), 500

@bp.route('/api/ehentai/favorites/addfav', methods=['POST'])
def add_favorite():
    """
    将画廊添加到 E-Hentai 收藏夹

    请求体格式:
    {
        "gid": 123456,
        "token": "abc123def456",
        "favcat": "0",
        "note": "备注信息（可选）"
    }
    """
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        try:
            data = request.get_json()
        except (ValueError, TypeError):
            return json_response({'error': '请提供有效的 JSON 数据'}), 400

        if not data:
            return json_response({'error': '请提供 JSON 数据'}), 400

        gid = data.get('gid')
        token = data.get('token')
        favcat = data.get('favcat', '0')  # 默认收藏夹
        note = data.get('note', '')      # 备注，可选

        if not gid or not token:
            return json_response({'error': '缺少必要参数：gid 和 token'}), 400

        # 获取 E-Hentai 工具实例
        eh_tools = current_app.config.get('EH_TOOLS')
        if not eh_tools:
            return json_response({'error': 'E-Hentai 工具未初始化'}), 500

        # 调用 add_to_favorites 方法
        success = eh_tools.add_to_favorites(
            gid=int(gid),
            token=token,
            favcat=str(favcat),
            note=note
        )

        if success:
            if global_logger:
                global_logger.info(f"成功将画廊 (gid: {gid}) 添加到收藏夹 (favcat: {favcat})")
            return json_response({
                'message': f'成功将画廊添加到收藏夹',
                'gid': gid,
                'favcat': favcat,
                'success': True
            }), 200
        else:
            if global_logger:
                global_logger.warning(f"将画廊 (gid: {gid}) 添加到收藏夹失败")
            return json_response({
                'error': '将画廊添加到收藏夹失败',
                'gid': gid,
                'favcat': favcat,
                'success': False
            }), 500

    except ValueError as e:
        if global_logger:
            global_logger.error(f"参数格式错误: {e}")
        return json_response({'error': f'参数格式错误: {str(e)}'}), 400
    except Exception as e:
        if global_logger:
            global_logger.error(f"添加收藏夹时发生错误: {e}")
        return json_response({'error': f'添加收藏夹时发生错误: {str(e)}'}), 500

@bp.route('/api/ehentai/favorites/fetch', methods=['GET'])
def fetch_undownloaded_favorites():
    """下载本地数据库中所有未下载的收藏"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        from scheduler import trigger_undownloaded_favorites_download

        if global_logger:
            global_logger.info("手动触发未下载收藏的下载任务")
        success_count, failed_count, total_count = trigger_undownloaded_favorites_download(logger=global_logger)

        if total_count == 0:
            return json_response({'message': '没有需要下载的收藏项目'}), 200

        return json_response({
            'message': f'已触发 {success_count} 个下载任务',
            'success': success_count,
            'failed': failed_count,
            'total': total_count
        }), 202

    except Exception as e:
        if global_logger:
            global_logger.error(f"触发未下载收藏下载任务失败: {e}")
        return json_response({'error': f'触发下载任务失败: {str(e)}'}), 500

@bp.route('/api/internal/favorite', methods=['POST'])
def handle_internal_favorite():
    """处理来自 notification.py 的内部 Komga 事件，用于收藏夹同步"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        data = request.get_json()
        if not data or 'event' not in data:
            return json_response({'error': 'No event type provided'}), 400

        event_type = data.get('event')
        event_data = data.get('data', {})

        if event_type == 'komga.new':
            return handle_favorite_downloaded(event_data)
        elif event_type == 'komga.delete':
            return handle_favorite_deleted(event_data)
        else:
            return json_response({'error': f"Unknown event type for internal favorite sync: {event_type}"}), 400

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error handling internal favorite: {e}")
        return json_response({'error': f'Failed to handle internal favorite: {str(e)}'}), 500

def handle_favorite_downloaded(data):
    """处理收藏夹项目已下载的逻辑 (komga.new)"""
    from utils import parse_gallery_url
    from database import task_db

    gallery_url = None
    links = data.get('metadata', {}).get('links', [])
    for link in links:
        if link.get('label') in ('e-hentai.org', 'exhentai.org', 'E-Hentai'):
            gallery_url = link.get('url')
            break

    if not gallery_url:
        return json_response({'error': 'E-Hentai/ExHentai URL not found in Komga metadata'}), 404

    gid, _ = parse_gallery_url(gallery_url)
    if not gid:
        return json_response({'error': f'Could not parse gid/token from URL: {gallery_url}'}), 400

    komga_book_id = data.get('id')
    if not komga_book_id:
        success = task_db.mark_favorite_as_downloaded(gid)
        if success:
            global_logger = current_app.config.get('GLOBAL_LOGGER')
            if global_logger:
                global_logger.info(f"成功将收藏夹项目 (gid: {gid}) 标记为已下载 (Komga Book ID 未提供)。")
            return json_response({'message': f'Favorite (gid: {gid}) marked as downloaded.'}), 200
        else:
            return json_response({'message': 'Favorite not found or already marked as downloaded.'}), 404

    # 从 Komga metadata 中获取标题
    komga_title = data.get('metadata', {}).get('title', '')

    success = task_db.update_favorite_komga_id(gid, komga_book_id, komga_title)
    if success:
        global_logger = current_app.config.get('GLOBAL_LOGGER')
        if global_logger:
            global_logger.info(f"成功将收藏夹项目 (gid: {gid}) 标记为已同步到 Komga (Book ID: {komga_book_id}, Title: {komga_title})。")
        return json_response({'message': f'Favorite (gid: {gid}) marked as synced with Komga book ID {komga_book_id}.'}), 200
    else:
        return json_response({'message': 'Favorite not found or failed to mark as synced.'}), 404

def handle_favorite_deleted(data):
    """处理收藏夹项目被删除的逻辑 (komga.delete)"""
    from database import task_db

    global_logger = current_app.config.get('GLOBAL_LOGGER')

    komga_book_id = data.get('id')
    if not komga_book_id:
        return json_response({'error': 'No book_id (id) provided for deletion event'}), 400

    favorite = task_db.get_favorite_by_komga_id(komga_book_id)
    if not favorite:
        if global_logger:
            global_logger.info(f"未找到与 Komga Book ID {komga_book_id} 关联的收藏夹记录，无需操作。")
        return json_response({'message': 'No favorite record found for this Komga book ID.'}), 200

    gid = favorite.get('gid')
    if not gid:
        return json_response({'error': 'Favorite record is missing gid.'}), 500

    eh_tools = current_app.config.get('EH_TOOLS')
    if not eh_tools:
        return json_response({'error': 'E-Hentai tools not initialized'}), 500

    delete_success = eh_tools.delete_from_favorites(str(gid))
    if delete_success:
        if global_logger:
            global_logger.info(f"成功从线上收藏夹删除 gid: {gid}。")
        task_db.delete_eh_favorites_by_gids([gid])
        if global_logger:
            global_logger.info(f"成功从本地数据库删除收藏夹记录 gid: {gid}。")
        return json_response({'message': f'Successfully deleted favorite (gid: {gid}) online and locally.'}), 200
    else:
        if global_logger:
            global_logger.error(f"从线上收藏夹删除 gid: {gid} 失败。")
        return json_response({'error': f'Failed to delete favorite (gid: {gid}) from online favorites.'}), 500


@bp.route('/api/ehentai/hath/status', methods=['GET'])
def get_hath_status():
    """
    获取 H@H 客户端状态
    
    返回所有客户端的当前状态和历史记录
    """
    from database import task_db
    
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 从数据库获取所有客户端状态
        clients = task_db.get_hath_status()
        
        if clients is None:
            return json_response({'error': '获取客户端状态失败'}), 500
        
        return json_response({
            'clients': clients,
            'total': len(clients) if isinstance(clients, list) else 0
        }), 200
        
    except Exception as e:
        if global_logger:
            global_logger.error(f"获取 H@H 客户端状态时发生错误: {e}")
        return json_response({'error': f'获取客户端状态失败: {str(e)}'}), 500


@bp.route('/api/ehentai/hath/check', methods=['GET'])
def check_hath_status():
    """
    手动触发 H@H 客户端状态检查并返回最新状态
    
    该接口会立即检查客户端状态，更新数据库，在状态变化时发送通知，并返回最新的状态列表。
    即使检查失败，也会返回数据库中的现有数据。
    """
    from database import task_db
    
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    
    if not current_app.config.get('HATH_CHECK_ENABLED', False):
        return json_response({'error': 'H@H 状态检查功能未启用'}), 400
    
    check_success = False
    check_error = None
    
    # 尝试执行检查
    try:
        from scheduler import check_hath_status_job
        check_hath_status_job()
        check_success = True
        
        if global_logger:
            global_logger.info("手动触发 H@H 客户端状态检查完成")
            
    except Exception as e:
        check_error = str(e)
        if global_logger:
            global_logger.error(f"H@H 状态检查失败: {e}，将返回数据库中的现有数据")
    
    # 无论检查是否成功，都尝试返回数据库中的状态
    try:
        clients = task_db.get_hath_status() or []
        
        response_data = {
            'clients': clients,
            'count': len(clients),
            'check_success': check_success
        }
        
        # 如果检查失败，附加错误信息
        if check_error:
            response_data['check_error'] = check_error
        
        return json_response(response_data), 200
        
    except Exception as e:
        # 数据库读取也失败了，这才是真正的错误
        if global_logger:
            global_logger.error(f"获取 H@H 状态数据失败: {e}")
        return json_response({'error': f'获取状态数据失败: {str(e)}'}), 500

