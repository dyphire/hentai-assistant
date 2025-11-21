"""
HDoujin RSS Feed Generator with integrated caching
"""
from datetime import datetime, timedelta
from email.utils import formatdate
from typing import Dict, List, Optional, Any
from jinja2 import Template
import threading
import hashlib
import time
import html

# Namespace mapping for HDoujin tags
NAMESPACE_MAP = {
    1: 'artist',
    2: 'group',
    3: 'parody',
    5: 'character',
    7: 'translator',
    8: 'male',
    9: 'female',
    10: 'mixed',
    11: 'language',
    12: 'other',
    13: 'category',
}

# RSS 2.0 Template
RSS_TEMPLATE = Template('''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>{{ title }}</title>
    <link>{{ link }}</link>
    <description>{{ description }}</description>
    <lastBuildDate>{{ build_date }}</lastBuildDate>
    {% for item in items %}
    <item>
      <title>{{ item.title }}</title>
      <link>{{ item.link }}</link>
      <guid isPermaLink="true">{{ item.guid }}</guid>
      <pubDate>{{ item.pub_date }}</pubDate>
      <description><![CDATA[{{ item.description }}]]></description>
      {% for category in item.categories %}
      <category>{{ category }}</category>
      {% endfor %}
    </item>
    {% endfor %}
  </channel>
</rss>''')


class RSSCache:
    """Thread-safe in-memory cache for RSS feeds"""
    
    def __init__(self, ttl: int = 3600):
        """
        Initialize RSS cache
        
        Args:
            ttl: Time to live in seconds (default: 3600)
        """
        self.ttl = ttl
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.Lock()
    
    def get(self, key: str) -> Optional[str]:
        """
        Get cached RSS content
        
        Args:
            key: Cache key
            
        Returns:
            Cached RSS content or None if expired/not found
        """
        with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if time.time() < entry['expires_at']:
                    return entry['content']
                else:
                    del self.cache[key]
            return None
    
    def set(self, key: str, content: str) -> None:
        """
        Store RSS content in cache
        
        Args:
            key: Cache key
            content: RSS content to cache
        """
        with self.lock:
            self.cache[key] = {
                'content': content,
                'expires_at': time.time() + self.ttl
            }
    
    def clear(self) -> None:
        """Clear all cached entries"""
        with self.lock:
            self.cache.clear()


def generate_hdoujin_rss(
    entries: List[Dict[str, Any]],
    title: str = "HDoujin RSS Feed",
    description: str = "Latest HDoujin entries",
    base_url: str = "https://hdoujin.co"
) -> str:
    """
    Generate RSS 2.0 feed from HDoujin API entries
    
    Args:
        entries: List of HDoujin book entries from API
        title: RSS feed title
        description: RSS feed description
        base_url: Base URL for HDoujin website
        
    Returns:
        RSS 2.0 XML string
    """
    items = []
    
    for entry in entries:
        # Extract basic info
        book_id = entry.get('id')
        book_key = entry.get('key', '')
        book_title = html.escape(entry.get('title', 'Untitled'))
        subtitle = entry.get('subtitle', '')
        created_at = entry.get('created_at')
        
        # Build link and GUID
        link = f"{base_url}/book/{book_key}"
        guid = link
        
        # Format publication date (RFC 822)
        pub_date = formatdate(timeval=created_at, localtime=False, usegmt=True) if created_at else formatdate()
        
        # Build description with thumbnail and subtitle
        thumbnails = entry.get('thumbnails', {})
        thumbnail_path = thumbnails.get('main', {}).get('path', '')
        thumbnail_url = f"{thumbnails.get('base', '')}{thumbnail_path}" if thumbnail_path else ""
        
        desc_parts = []
        if thumbnail_url:
            desc_parts.append(f'<img src="{html.escape(thumbnail_url)}" />')
        if subtitle:
            desc_parts.append(f'<p>{html.escape(subtitle)}</p>')
        
        description_content = '<br/>'.join(desc_parts) if desc_parts else book_title
        
        # Process tags into categories
        categories = []
        tags = entry.get('tags', [])
        for tag in tags:
            namespace_id = tag.get('namespace')
            tag_name = tag.get('name', '')
            
            # Map namespace to readable name
            namespace_name = NAMESPACE_MAP.get(namespace_id, 'unknown')
            
            # Format as "namespace:tagname"
            category = f"{namespace_name}:{tag_name}"
            categories.append(html.escape(category))
        
        items.append({
            'title': book_title,
            'link': link,
            'guid': guid,
            'pub_date': pub_date,
            'description': description_content,
            'categories': categories
        })
    
    # Render RSS template
    rss_content = RSS_TEMPLATE.render(
        title=html.escape(title),
        link=base_url,
        description=html.escape(description),
        build_date=formatdate(),
        items=items
    )
    
    return rss_content
