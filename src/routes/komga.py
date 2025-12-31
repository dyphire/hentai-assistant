from flask import Blueprint, request, current_app as app
import json
import logging

from database import task_db

bp = Blueprint('komga', __name__)
logger = logging.getLogger(__name__)

def json_response(data, status=200):
    from flask import Response
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        mimetype="application/json"
    )

@bp.route('/api/komga/index/collect', methods=['POST'])
def collect_url_index():
    """增量收集 Komga 书籍 URL 索引"""
    try:
        # 检查 Komga 是否已启用
        if not app.config.get('KOMGA_TOGGLE', False):
            return json_response({'error': 'Komga is not enabled'}, 400)
        
        # 获取 Komga API 实例
        from providers import komga
        komga_api = komga.KomgaAPI(
            server=app.config.get('KOMGA_SERVER'),
            username=app.config.get('KOMGA_USERNAME'),
            password=app.config.get('KOMGA_PASSWORD'),
            logger=logger
        )
        
        page = 0
        size = 50
        total_collected = 0
        total_skipped = 0
        
        logger.info("开始收集 Komga URL 索引...")
        
        while True:
            # 1. 获取当前页数据
            data = komga_api.get_latest_books(page=page, size=size)
            books = data.get('content', [])

            
            if not books:
                logger.info(f"第 {page} 页没有数据，收集完成")
                break  # 没有更多数据
            
            # 2. 提取 URL 并检查是否已存在
            urls_to_check = []
            book_map = {}  # {normalized_url: book_data}
            
            for book in books:
                book_id = book.get('id')
                metadata = book.get('metadata', {})
                links = metadata.get('links', [])
                
                for link in links:
                    url = link.get('url')
                    if url:
                        normalized_url, site_type = task_db.normalize_url(url)
                        urls_to_check.append(normalized_url)
                        book_map[normalized_url] = {
                            'book_id': book_id,
                            'original_url': url,
                            'site_type': site_type
                        }
            
            if not urls_to_check:
                logger.info(f"第 {page} 页没有有效的 URL，继续下一页")
                page += 1
                continue
            
            # 3. 检查哪些 URL 已存在
            existing_urls = task_db.check_urls_exist(urls_to_check)
            
            # 4. 统计已存在的数量
            existing_count = sum(1 for exists in existing_urls.values() if exists)
            
            logger.info(f"第 {page} 页: 总共 {len(urls_to_check)} 个 URL，已存在 {existing_count} 个")
            
            # 5. 如果这一页全部已存在，停止收集
            if existing_count == len(urls_to_check) and len(urls_to_check) >= size * 0.8:
                logger.info(f"第 {page} 页的大部分记录都已存在，停止收集")
                break
            
            # 6. 插入新的 URL 索引
            new_urls = []
            for normalized_url, book_data in book_map.items():
                if not existing_urls.get(normalized_url, False):
                    new_urls.append({
                        'url': normalized_url,
                        'book_id': book_data['book_id'],
                        'original_url': book_data['original_url'],
                        'site_type': book_data['site_type']
                    })
            
            if new_urls:
                success = task_db.upsert_komga_url_index(new_urls)
                if success:
                    total_collected += len(new_urls)
                    logger.info(f"第 {page} 页: 新增 {len(new_urls)} 条索引")
                else:
                    logger.error(f"第 {page} 页: 插入索引失败")
            
            total_skipped += existing_count
            
            # 7. 继续下一页
            page += 1
        
        logger.info(f"收集完成: 总共扫描 {page} 页，新增 {total_collected} 条，跳过 {total_skipped} 条")
        
        return json_response({
            'success': True,
            'total_collected': total_collected,
            'total_skipped': total_skipped,
            'pages_scanned': page
        })
    
    except Exception as e:
        logger.error(f"收集 URL 索引时出错: {e}", exc_info=True)
        return json_response({'error': str(e)}, 500)


@bp.route('/api/komga/index/query', methods=['POST'])
def query_url_index():
    """批量查询 URL 对应的 Book ID"""
    try:
        data = request.get_json()
        urls = data.get('urls', [])
        
        if not urls:
            return json_response({'error': 'urls is required'}, 400)
        
        if not isinstance(urls, list):
            return json_response({'error': 'urls must be an array'}, 400)
        
        # 查询数据库
        results_data = task_db.query_book_ids_by_urls(urls)
        
        # 构建响应
        results = {}
        found_count = 0
        
        komga_server = app.config.get('KOMGA_SERVER', '')
        
        for original_url in urls:
            normalized_url, _ = task_db.normalize_url(original_url)
            book_info = results_data.get(normalized_url)
            
            if book_info:
                found_count += 1
                results[original_url] = {
                    'found': True,
                    'book_id': book_info['book_id'],
                    'komga_url': f"{komga_server}/book/{book_info['book_id']}",
                    'normalized_url': normalized_url
                }
            else:
                results[original_url] = {
                    'found': False,
                    'book_id': None,
                    'komga_url': None,
                    'normalized_url': normalized_url
                }
        
        return json_response({
            'summary': {
                'total': len(urls),
                'found': found_count,
                'missing': len(urls) - found_count
            },
            'results': results
        })
    
    except Exception as e:
        logger.error(f"查询 URL 索引时出错: {e}", exc_info=True)
        return json_response({'error': str(e)}, 500)
