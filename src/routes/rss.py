"""
RSS Feed Routes
"""
from flask import Blueprint, request, Response, current_app
import hashlib
from typing import Optional
from providers.hdoujin_api import books_search
from rss_generator import generate_hdoujin_rss, RSSCache
from config import load_config

rss_bp = Blueprint('rss', __name__)

# Global RSS cache instance (initialized in main.py)
RSS_CACHE: Optional[RSSCache] = None


def init_rss_cache(cache_ttl: int = 3600):
    """Initialize global RSS cache"""
    global RSS_CACHE
    RSS_CACHE = RSSCache(ttl=cache_ttl)


@rss_bp.route('/rss/hdoujin', methods=['GET'])
@rss_bp.route('/rss/hdoujin/<path:api_params>', methods=['GET'])
def hdoujin_rss(api_params: str = ''):
    """
    HDoujin RSS feed endpoint
    
    Path format: /rss/hdoujin/param1=value1&param2=value2
    Query parameters (RSS-specific):
    - prefer_title: "japanese" or "default"
    - max_items: maximum number of items to return
    
    API parameters (in path) are passed through to HDoujin API:
    - s: search term
    - lang: language filter (8=Chinese, 2=English, etc.)
    - include: included tag IDs (comma-separated)
    - exclude: excluded tag IDs (comma-separated)
    - page: page number
    - sort: sort method
    """
    try:
        # Parse API parameters from path
        api_params_dict = {}
        if api_params:
            for param in api_params.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    api_params_dict[key] = value
        
        # Get RSS-specific query parameters
        prefer_title = request.args.get('prefer_title', '')
        max_items = request.args.get('max_items', type=int)
        
        # If prefer_title not specified, check config
        if not prefer_title:
            try:
                config = load_config()
                prefer_japanese = config.get('general', {}).get('prefer_japanese_title', True)
                prefer_title = 'japanese' if prefer_japanese else 'default'
            except:
                prefer_title = 'default'
        
        # Generate cache key from API params and prefer_title
        cache_data = {
            'api_params': sorted(api_params_dict.items()),
            'prefer_title': prefer_title,
            'max_items': max_items
        }
        cache_key = hashlib.md5(
            str(cache_data).encode('utf-8')
        ).hexdigest()
        
        # Check cache
        if RSS_CACHE:
            cached_rss = RSS_CACHE.get(cache_key)
            if cached_rss:
                return Response(cached_rss, mimetype='application/xml')
        
        # Call HDoujin API
        result = books_search(api_params_dict)
        
        if result.get('code') != 200:
            error_msg = result.get('message', 'Unknown error')
            error_rss = generate_hdoujin_rss(
                [],
                title="HDoujin RSS - Error",
                description=f"Error: {error_msg}",
                prefer_title=prefer_title
            )
            return Response(error_rss, mimetype='application/xml', status=500)
        
        # Extract entries
        entries = result.get('body', {}).get('entries', [])
        
        # Limit number of items (optional)
        if max_items and max_items > 0:
            entries = entries[:max_items]
        
        # Generate RSS
        search_term = api_params_dict.get('s', '')
        title = f"HDoujin RSS{' - ' + search_term if search_term else ''}"
        description = f"HDoujin search results{' for: ' + search_term if search_term else ''}"
        
        rss_content = generate_hdoujin_rss(
            entries,
            title=title,
            description=description,
            prefer_title=prefer_title
        )
        
        # Cache the result
        if RSS_CACHE:
            RSS_CACHE.set(cache_key, rss_content)
        
        return Response(rss_content, mimetype='application/xml')
        
    except Exception as e:
        # Return error as RSS
        # Use default prefer_title for error messages
        try:
            config = load_config()
            prefer_japanese = config.get('general', {}).get('prefer_japanese_title', True)
            error_prefer = 'japanese' if prefer_japanese else 'default'
        except:
            error_prefer = 'default'
            
        error_rss = generate_hdoujin_rss(
            [],
            title="HDoujin RSS - Error",
            description=f"Internal error: {str(e)}",
            prefer_title=error_prefer
        )
        return Response(error_rss, mimetype='application/xml', status=500)
