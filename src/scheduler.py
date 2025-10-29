from flask_apscheduler import APScheduler
import logging
import requests
from flask import current_app
from providers.komga import KomgaAPI
from database import task_db

from utils import parse_gallery_url
from metadata_extractor import parse_filename

# 初始化调度器
scheduler = APScheduler()

def trigger_undownloaded_favorites_download(logger=None, config=None):
    """
    触发未下载收藏的下载任务。
    可被 scheduler 自动调用，也可被 API 手动调用。
    返回 (success_count, failed_count, total_count)
    """
    from flask import current_app
    
    if logger is None:
        logger = current_app.logger
    
    if config is None:
        config = current_app.config
    
    # 使用全局 EH_TOOLS 实例
    ehentai_tool = config.get('EH_TOOLS')
    if not ehentai_tool:
        logger.warning("EH_TOOLS 未初始化，无法触发下载任务。")
        return 0, 0, 0
    
    undownloaded_favorites = task_db.get_undownloaded_favorites()
    if not undownloaded_favorites:
        logger.info("没有需要下载的新收藏夹项目。")
        return 0, 0, 0
    
    logger.info(f"发现 {len(undownloaded_favorites)} 个新的收藏夹项目需要下载。")
    port = config.get('PORT', 5001)
    api_base_url = f"http://127.0.0.1:{port}"
    
    success_count = 0
    failed_count = 0
    
    for fav in undownloaded_favorites:
        gid = fav['gid']
        token = fav['token']
        # 默认使用 e-hentai.org
        url = f"https://e-hentai.org/g/{gid}/{token}/"
        
        try:
            logger.info(f"为新画廊创建下载任务: {url}")
            favcat_id = fav.get('favcat')
            response = requests.get(f"{api_base_url}/api/download", params={"url": url, "fav": favcat_id, "download": "true"}, timeout=10)
            
            if response.status_code == 202:
                logger.info(f"成功为 {url} 创建下载任务。")
                success_count += 1
            else:
                logger.error(f"为 {url} 创建下载任务失败: {response.status_code} - {response.text}")
                failed_count += 1
        except requests.RequestException as re:
            logger.error(f"调用下载 API 时发生网络错误 for url {url}: {re}")
            failed_count += 1
    
    return success_count, failed_count, len(undownloaded_favorites)

def sync_eh_favorites_job(auto_download=None):
    """
    定时同步 E-Hentai 收藏夹的任务。
    该函数将由调度器定时调用。
    
    参数:
    - auto_download: 是否自动下载（None 表示使用配置中的值）
    """
    # APScheduler 在后台线程运行，需要手动推入 app context
    with scheduler.app.app_context():
        logger = current_app.logger
        logger.info("定时任务触发: 开始同步 E-Hentai 收藏夹...")

        try:
            config = current_app.config
            
            # 确定是否自动下载
            if auto_download is None:
                auto_download = config.get('EH_FAV_AUTO_DOWNLOAD', False)
            # 使用全局 EH_TOOLS 实例
            ehentai_tool = config.get('EH_TOOLS')
            if not ehentai_tool:
                logger.warning("EH_TOOLS 未初始化，跳过收藏夹同步。")
                return
            
            # 1. 从配置中获取要同步的收藏夹分类
            favcat_list = config.get('EH_FAV_SYNC_FAVCAT', [])
            if not favcat_list:
                logger.info("没有配置要同步的 E-Hentai 收藏夹分类，任务结束。")
                return

            logger.info(f"准备同步以下收藏夹分类: {favcat_list}")

            # 3. 获取数据库中已存在的画廊
            local_galleries_raw = task_db.get_eh_favorites_by_favcat(favcat_list)
            local_galleries = {g['gid']: g for g in local_galleries_raw}
            existing_gids = set(local_galleries.keys())
            
            # 获取首次扫描页数配置
            initial_scan_pages = config.get('EH_FAV_INITIAL_SCAN_PAGES', 1)
            
            if existing_gids:
                logger.info(f"数据库中已有 {len(existing_gids)} 个收藏画廊，将进行增量扫描（连续匹配5个相同GID时停止）。")
            else:
                if initial_scan_pages == 0:
                    logger.info(f"数据库中没有收藏记录，将进行全量扫描（所有页）。")
                else:
                    logger.info(f"数据库中没有收藏记录，将扫描前 {initial_scan_pages} 页。")

            # 4. 获取所有画廊，并以 GID 作为键（传入已存在的GID集合和首次扫描页数）
            # 注意：当传入 existing_gids 时，get_favorites 会进行增量扫描，只返回新的画廊
            is_incremental = existing_gids is not None and len(existing_gids) > 0
            
            online_galleries_raw = ehentai_tool.get_favorites(
                favcat_list,
                existing_gids=existing_gids if existing_gids else None,
                initial_scan_pages=initial_scan_pages
            )
            online_galleries = {}
            for g in online_galleries_raw:
                gid, _ = parse_gallery_url(g.get('url', ''))
                if gid:
                    online_galleries[gid] = g
            
            if is_incremental:
                logger.info(f"增量扫描完成，从线上收藏夹中获取到 {len(online_galleries)} 个新的画廊。")
            else:
                logger.info(f"全量扫描完成，从线上收藏夹中获取到 {len(online_galleries)} 个画廊。")

            # 5. 执行数据库操作
            # 使用 UPSERT 逻辑一次性处理新增和信息变更（如 favcat, added time）
            if online_galleries:
                galleries_to_upsert = list(online_galleries.values())
                
                if task_db.upsert_eh_favorites(galleries_to_upsert):
                    logger.info(f"成功向数据库同步（新增/更新）了 {len(galleries_to_upsert)} 个收藏夹画廊。")
                else:
                    logger.error("向数据库同步（新增/更新）画廊时发生错误。")
            else:
                logger.info("线上收藏夹为空或没有新画廊，无需同步。")

            # 6. 只有在全量扫描时才删除本地不存在于线上的画廊
            # 增量扫描时不删除，因为我们没有获取完整的线上列表
            if not is_incremental:
                online_gids = set(online_galleries.keys())
                local_gids = set(local_galleries.keys())
                removed_gids = local_gids - online_gids
                
                if removed_gids:
                    if task_db.delete_eh_favorites_by_gids(list(removed_gids)):
                        logger.info(f"成功从数据库移除了 {len(removed_gids)} 个已不存在的收藏夹画廊。")
                    else:
                        logger.error("从数据库移除旧画廊时发生错误。")
                else:
                    logger.info("没有需要移除的收藏夹画廊。")
            else:
                logger.info("增量扫描模式，跳过画廊删除检查。")

            # 7. 检查 Komga 匹配
            komga_enabled = config.get('KOMGA_TOGGLE', False)
            if komga_enabled:
                logger.info("开始检查 Komga 中的收藏...")
                komga_server = config.get('KOMGA_SERVER')
                komga_username = config.get('KOMGA_USERNAME')
                komga_password = config.get('KOMGA_PASSWORD')

                if all([komga_server, komga_username, komga_password]):
                    komga_api = KomgaAPI(server=komga_server, username=komga_username, password=komga_password, logger=logger)
                    if komga_api._valid_session():
                        favorites_to_check = task_db.get_favorites_without_komga_id()
                        if favorites_to_check:
                            logger.info(f"发现 {len(favorites_to_check)} 个项目需要在 Komga 中检查。")
                            match_count = 0
                            for fav in favorites_to_check:
                                gid, token = fav['gid'], fav['token']
                                komga_title = fav.get('title')  # Komga 标题
                                originaltitle = fav.get('originaltitle')  # 线上收藏夹原始标题
                                expected_url_e = f"https://e-hentai.org/g/{gid}/{token}/"
                                expected_url_ex = f"https://exhentai.org/g/{gid}/{token}/"
                                
                                try:
                                    found_match = False
                                    matched_book_id = None
                                    matched_book_title = None
                                    
                                    # 确定搜索标题
                                    search_title = None
                                    if komga_title:
                                        # 优先使用 Komga 标题
                                        search_title = komga_title
                                    elif originaltitle:
                                        # 如果没有 Komga 标题，使用 parse_filename 从原始标题中提取
                                        parsed_title, _, _ = parse_filename(originaltitle, None)
                                        search_title = parsed_title if parsed_title else None
                                    
                                    # 用标题搜索
                                    if search_title:
                                        search_results = komga_api.search_book_by_title(search_title)
                                        logger.info(f"搜索标题 '{search_title}' (GID: {gid})，找到 {len(search_results)} 个结果")
                                        for book in search_results:
                                            book_id = book.get('id')
                                            links = book.get('metadata', {}).get('links', [])
                                            if any(link.get('url', '') in (expected_url_e, expected_url_ex) for link in links):
                                                found_match = True
                                                matched_book_id = book_id
                                                matched_book_title = book.get('metadata', {}).get('title', '')
                                                logger.info(f"在 Komga 中找到匹配项: '{search_title}' (GID: {gid}) -> Komga Book ID: {book_id}")
                                                break
                                    
                                    # 如果找到匹配，更新数据库
                                    if found_match and matched_book_id:
                                        if task_db.update_favorite_komga_id(gid, matched_book_id, matched_book_title):
                                            match_count += 1
                                    
                                except Exception as e:
                                    logger.error(f"处理 GID {gid} (search_title: '{search_title}') 时发生错误: {e}", exc_info=True)
                            if match_count > 0:
                                logger.info(f"Komga 检查完成，成功匹配并更新了 {match_count} 个项目。")
                        else:
                            logger.info("没有需要检查的 Komga 项目。")
                    else:
                        logger.warning("无法连接到 Komga 或凭据无效，跳过检查。")
                else:
                    logger.warning("Komga 配置不完整，跳过检查。")
            else:
                logger.info("Komga 集成未启用，跳过检查。")

            # 8. 触发未下载收藏的下载任务（如果启用了自动下载）
            if auto_download:
                trigger_undownloaded_favorites_download(logger=logger, config=config)
            else:
                logger.info("自动下载收藏功能未启用，跳过下载任务创建。")

            logger.info("E-Hentai 收藏夹同步任务执行完毕。")

        except Exception as e:
            logger.error(f"同步 E-Hentai 收藏夹时发生错误: {e}", exc_info=True)


def refresh_eh_cookie_job():
    """
    每日验证 E-Hentai cookie 的有效性并更新资金信息。
    通过调用 /api/ehentai/refresh API 来执行验证。
    """
    with scheduler.app.app_context():
        logger = current_app.logger
        logger.info("定时任务触发: 开始验证 E-Hentai Cookie...")

        try:
            config = current_app.config
            port = config.get('PORT', 5001)
            api_url = f"http://127.0.0.1:{port}/api/ehentai/refresh"

            response = requests.get(api_url, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    logger.info(f"E-Hentai Cookie 验证成功: EH={result.get('eh_valid')}, ExH={result.get('exh_valid')}, Funds={result.get('funds')}")
                else:
                    logger.warning(f"E-Hentai Cookie 验证失败: {result.get('message')}")
            else:
                logger.error(f"调用 /api/ehentai/refresh 失败: HTTP {response.status_code}")

        except requests.RequestException as e:
            logger.error(f"调用 /api/ehentai/refresh 时发生网络错误: {e}")
        except Exception as e:
            logger.error(f"验证 E-Hentai Cookie 时发生错误: {e}", exc_info=True)


def refresh_hdoujin_token_job():
    """
    每日验证 HDoujin token 的有效性并自动刷新。
    通过调用 HDoujinTools 的 is_valid_cookie 方法来执行验证。
    """
    with scheduler.app.app_context():
        logger = current_app.logger
        logger.info("定时任务触发: 开始验证 HDoujin Token...")

        try:
            config = current_app.config
            hdoujin_tool = config.get('HD_TOOLS')
            if not hdoujin_tool:
                logger.warning("HD_TOOLS 未初始化，跳过 HDoujin Token 验证。")
                return

            # 验证并自动刷新 token
            is_valid = hdoujin_tool.is_valid_cookie()

            if is_valid:
                # 获取更新后的 token 并保存到配置
                updated_tokens = hdoujin_tool.get_tokens()
                config['HDOUJIN_SESSION_TOKEN'] = updated_tokens.get('session_token', '')
                config['HDOUJIN_REFRESH_TOKEN'] = updated_tokens.get('refresh_token', '')
                config['HDOUJIN_CLEARANCE_TOKEN'] = updated_tokens.get('clearance_token', '')

                logger.info("HDoujin Token 验证成功")
            else:
                logger.warning("HDoujin Token 验证失败")

        except Exception as e:
            logger.error(f"验证 HDoujin Token 时发生错误: {e}", exc_info=True)


def update_scheduler_jobs(app):
    """
    根据当前应用配置更新调度器中的任务。
    保存配置后，如果任务被启用，会立即触发一次执行。
    """
    with app.app_context():
        job_id = 'sync_eh_favorites'
        is_enabled = app.config.get('EH_FAV_SYNC_ENABLED', False)
        sync_interval = app.config.get('EH_FAV_SYNC_INTERVAL', 24)
        existing_job = scheduler.get_job(job_id)

        # 无论如何，先移除已存在的任务，以便重新安排
        if existing_job:
            scheduler.remove_job(job_id)

        # 如果功能是启用的，则添加任务并设置立即执行
        if is_enabled:
            scheduler.add_job(
                id=job_id,
                func=sync_eh_favorites_job,
                trigger='interval',
                hours=sync_interval,
                misfire_grace_time=3600
            )
            if existing_job:
                app.logger.info(f"E-Hentai 收藏夹同步任务将以 {sync_interval} 小时的间隔运行。")
        else:
            # 如果功能被禁用，日志会告知用户任务已被移除（如果它之前存在）
            if existing_job:
                app.logger.info("E-Hentai 收藏夹同步任务已禁用并移除。")
        
        # 添加每日 E-Hentai Cookie 验证任务
        cookie_job_id = 'refresh_eh_cookie_daily'
        existing_cookie_job = scheduler.get_job(cookie_job_id)
        
        if existing_cookie_job:
            scheduler.remove_job(cookie_job_id)
        
        # 添加每日运行的 Cookie 验证任务（24小时间隔）
        scheduler.add_job(
            id=cookie_job_id,
            func=refresh_eh_cookie_job,
            trigger='interval',
            hours=24,
            misfire_grace_time=3600
        )
        app.logger.info("E-Hentai Cookie 验证任务已添加，将每 24 小时运行一次。")

        # 添加每日 HDoujin Token 验证任务
        hdoujin_job_id = 'refresh_hdoujin_token_daily'
        existing_hdoujin_job = scheduler.get_job(hdoujin_job_id)

        if existing_hdoujin_job:
            scheduler.remove_job(hdoujin_job_id)

        # 添加每日运行的 HDoujin Token 验证任务（24小时间隔）
        scheduler.add_job(
            id=hdoujin_job_id,
            func=refresh_hdoujin_token_job,
            trigger='interval',
            hours=24,
            misfire_grace_time=3600
        )
        app.logger.info("HDoujin Token 验证任务已添加，将每 24 小时运行一次。")


def init_scheduler(app):
    """
    初始化并启动调度器。
    """
    if not scheduler.running:
        scheduler.init_app(app)
        scheduler.start()
        app.logger.info("调度器已初始化并启动。")
