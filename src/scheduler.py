from flask_apscheduler import APScheduler
import logging
import requests
from flask import current_app
from datetime import datetime
from providers.ehentai import EHentaiTools
from providers.komga import KomgaAPI
from database import task_db

import html
from utils import parse_gallery_url
from metadata_extractor import parse_filename
from providers.ehtranslator import EhTagTranslator

# 初始化调度器
scheduler = APScheduler()

def sync_eh_favorites_job():
    """
    定时同步 E-Hentai 收藏夹的任务。
    该函数将由调度器定时调用。
    """
    # APScheduler 在后台线程运行，需要手动推入 app context
    with scheduler.app.app_context():
        logger = current_app.logger
        logger.info("定时任务触发: 开始同步 E-Hentai 收藏夹...")

        try:
            config = current_app.config
            ehentai_tool = EHentaiTools(cookie=config.get('EH_COOKIE'), logger=logger)
            # 在同步任务中，我们需要一个临时的 translator 实例
            eh_translator = EhTagTranslator(enable_translation=config.get('TAGS_TRANSLATION', True))
            
            # 1. 检查 cookie 是否有效
            eh_valid, exh_valid, _ = ehentai_tool.is_valid_cookie()
            if not (eh_valid or exh_valid):
                logger.warning("E-Hentai/ExHentai cookie 无效，跳过收藏夹同步。")
                return

            # 2. 从配置中获取要同步的收藏夹分类
            favcat_list = config.get('EH_FAV_SYNC_FAVCAT', [])
            if not favcat_list:
                logger.info("没有配置要同步的 E-Hentai 收藏夹分类，任务结束。")
                return

            logger.info(f"准备同步以下收藏夹分类: {favcat_list}")

            # 3. 获取所有画廊，并以 GID 作为键
            online_galleries_raw = ehentai_tool.get_favorites(favcat_list)
            online_galleries = {}
            for g in online_galleries_raw:
                gid, _ = parse_gallery_url(g.get('url', ''))
                if gid:
                    online_galleries[gid] = g
            logger.info(f"从线上收藏夹中获取到 {len(online_galleries)} 个有效画廊。")

            # 4. 获取数据库中已存在的画廊
            local_galleries_raw = task_db.get_eh_favorites_by_favcat(favcat_list)
            local_galleries = {g['gid']: g for g in local_galleries_raw}
            logger.info(f"从数据库中获取到 {len(local_galleries)} 个本地收藏画廊。")

            # 5. 计算差异
            online_gids = set(online_galleries.keys())
            local_gids = set(local_galleries.keys())
            
            new_gids = online_gids - local_gids
            removed_gids = local_gids - online_gids
            existing_gids = online_gids.intersection(local_gids)

            # 6. 检查并更新已存在画廊的 favcat
            updated_count = 0
            if existing_gids:
                for gid in existing_gids:
                    online_favcat = online_galleries[gid].get('favcat')
                    local_favcat = local_galleries[gid].get('favcat')
                    if str(online_favcat) != str(local_favcat):
                        if task_db.update_favorite_favcat(gid, online_favcat):
                            logger.info(f"画廊 GID {gid} 的收藏夹分类已从 {local_favcat} 更新为 {online_favcat}。")
                            updated_count += 1
                        else:
                            logger.error(f"更新 GID {gid} 的收藏夹分类失败。")
            if updated_count > 0:
                logger.info(f"成功更新了 {updated_count} 个画廊的收藏夹分类。")
            else:
                logger.info("没有画廊的收藏夹分类需要更新。")

            # 7. 执行数据库操作 (新增和删除)
            if new_gids:
                # 在添加到数据库之前，处理标题
                galleries_with_parsed_titles = []
                for gid in new_gids:
                    gallery_data = online_galleries[gid]
                    raw_title = gallery_data.get('title', '')
                    # 使用 metadata_extractor 来生成标准化的标题
                    clean_title, _, _ = parse_filename(html.unescape(raw_title), eh_translator)
                    gallery_data['title'] = clean_title
                    galleries_with_parsed_titles.append(gallery_data)

                if task_db.add_eh_favorites(galleries_with_parsed_titles):
                    logger.info(f"成功向数据库添加了 {len(new_gids)} 个新的收藏夹画廊。")
                else:
                    logger.error("向数据库添加新画廊时发生错误。")
            else:
                logger.info("没有发现新的收藏夹画廊。")

            if removed_gids:
                if task_db.delete_eh_favorites_by_gids(list(removed_gids)):
                    logger.info(f"成功从数据库移除了 {len(removed_gids)} 个已不存在的收藏夹画廊。")
                else:
                    logger.error("从数据库移除旧画廊时发生错误。")
            else:
                logger.info("没有需要移除的收藏夹画廊。")

            # 8. 检查 Komga 匹配
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
                                gid, token, title = fav['gid'], fav['token'], fav['title']
                                expected_url_e = f"https://e-hentai.org/g/{gid}/{token}/"
                                expected_url_ex = f"https://exhentai.org/g/{gid}/{token}/"
                                
                                try:
                                    search_results = komga_api.search_book_by_title(title)
                                    for book in search_results:
                                        book_id = book.get('id')
                                        links = book.get('metadata', {}).get('links', [])
                                        found_match = any(link.get('url', '') in (expected_url_e, expected_url_ex) for link in links)
                                        if found_match:
                                            logger.info(f"在 Komga 中找到匹配项: '{title}' (GID: {gid}) -> Komga Book ID: {book_id}")
                                            if task_db.update_favorite_komga_id(gid, book_id):
                                                match_count += 1
                                            break
                                except Exception as e:
                                    logger.error(f"处理 GID {gid} ('{title}') 时发生错误: {e}", exc_info=True)
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

            # 9. 触发未下载收藏的下载任务
            undownloaded_favorites = task_db.get_undownloaded_favorites()
            if undownloaded_favorites:
                logger.info(f"发现 {len(undownloaded_favorites)} 个新的收藏夹项目需要下载。")
                port = config.get('PORT', 5001)
                api_base_url = f"http://127.0.0.1:{port}"
                
                for fav in undownloaded_favorites:
                    gid = fav['gid']
                    token = fav['token']
                    # 动态构建 URL (优先使用 ExHentai)
                    domain = "exhentai.org" if exh_valid else "e-hentai.org"
                    url = f"https://{domain}/g/{gid}/{token}/"
                    
                    try:
                        logger.info(f"为新画廊创建下载任务: {url}")
                        favcat_id = fav.get('favcat')
                        response = requests.get(f"{api_base_url}/api/download", params={"url": url, "fav": favcat_id}, timeout=10)
                        
                        if response.status_code == 202:
                            logger.info(f"成功为 {url} 创建下载任务。现在将其标记为已下载。")
                            task_db.mark_favorite_as_downloaded(gid)
                        else:
                            logger.error(f"为 {url} 创建下载任务失败: {response.status_code} - {response.text}")
                    except requests.RequestException as re:
                        logger.error(f"调用下载 API 时发生网络错误 for url {url}: {re}")
            else:
                logger.info("没有需要下载的新收藏夹项目。")

            logger.info("E-Hentai 收藏夹同步任务执行完毕。")

        except Exception as e:
            logger.error(f"同步 E-Hentai 收藏夹时发生错误: {e}", exc_info=True)


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
                app.logger.info(f"E-Hentai 收藏夹同步任务已更新，将立即执行一次，然后按每 {sync_interval} 小时的间隔运行。")
        else:
            # 如果功能被禁用，日志会告知用户任务已被移除（如果它之前存在）
            if existing_job:
                app.logger.info("E-Hentai 收藏夹同步任务已禁用并移除。")


def init_scheduler(app):
    """
    初始化并启动调度器。
    """
    if not scheduler.running:
        scheduler.init_app(app)
        scheduler.start()
        app.logger.info("调度器已初始化并启动。")
