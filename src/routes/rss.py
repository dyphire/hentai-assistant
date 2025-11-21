"""
RSS Feed Routes
"""
from flask import Blueprint, request, Response
import hashlib
from typing import Optional
from providers.hdoujin_api import books_search
from rss_generator import generate_hdoujin_rss, RSSCache

rss_bp = Blueprint('rss', __name__)

# Global RSS cache instance (initialized in main.py)
RSS_CACHE: Optional[RSSCache] = None


def init_rss_cache(cache_ttl: int = 3600):
    """Initialize global RSS cache"""
    global RSS_CACHE
    RSS_CACHE = RSSCache(ttl=cache_ttl)


@rss_bp.route('/rss/hdoujin', methods=['GET'])
def hdoujin_rss():
    """
    HDoujin RSS feed endpoint
    
    Query parameters are passed through to HDoujin API:
    - s: search term
    - lang: language filter
    - tags: tag filters
    - etc.
    """
    try:
        # Get all query parameters
        params = request.args.to_dict(flat=False)
        
        # Flatten single-value lists
        flat_params = {}
        for key, value in params.items():
            flat_params[key] = value[0] if len(value) == 1 else value
        
        # Generate cache key from sorted parameters
        cache_key = hashlib.md5(
            str(sorted(flat_params.items())).encode('utf-8')
        ).hexdigest()
        
        # Check cache
        if RSS_CACHE:
            cached_rss = RSS_CACHE.get(cache_key)
            if cached_rss:
                return Response(cached_rss, mimetype='application/xml')
        
        # Call HDoujin API
        result = books_search(flat_params)
        
        if result.get('code') != 200:
            error_msg = result.get('message', 'Unknown error')
            error_rss = generate_hdoujin_rss(
                [],
                title="HDoujin RSS - Error",
                description=f"Error: {error_msg}"
            )
            return Response(error_rss, mimetype='application/xml', status=500)
        
        # Extract entries
        entries = result.get('body', {}).get('entries', [])
        
        # Limit number of items (optional)
        max_items = request.args.get('max_items', type=int)
        if max_items and max_items > 0:
            entries = entries[:max_items]
        
        # Generate RSS
        search_term = flat_params.get('s', '')
        title = f"HDoujin RSS{' - ' + search_term if search_term else ''}"
        description = f"HDoujin search results{' for: ' + search_term if search_term else ''}"
        
        rss_content = generate_hdoujin_rss(
            entries,
            title=title,
            description=description
        )
        
        # Cache the result
        if RSS_CACHE:
            RSS_CACHE.set(cache_key, rss_content)
        
        return Response(rss_content, mimetype='application/xml')
        
    except Exception as e:
        # Return error as RSS
        error_rss = generate_hdoujin_rss(
            [],
            title="HDoujin RSS - Error",
            description=f"Internal error: {str(e)}"
        )
        return Response(error_rss, mimetype='application/xml', status=500)
