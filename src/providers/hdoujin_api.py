from typing import Optional, Dict, Any
import cloudscraper


API_BASE = "https://api.hdoujin.org"
AUTH_BASE = "https://auth.hdoujin.org"


# 全局 User-Agent
_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def set_user_agent(user_agent: str):
    """设置全局 User-Agent"""
    global _user_agent
    if user_agent:
        _user_agent = user_agent

def _create_session() -> cloudscraper.CloudScraper:
    """
    使用 cloudscraper 来处理 Cloudflare 基本验证
    创建绕过 Cloudflare 的 session

    注意：cloudscraper 只能绕过 Cloudflare 的基本 JS Challenge，
    无法处理 Cloudflare Turnstile 人机验证。

    Clearance token 必须通过以下方式获取：
    1. 在浏览器中访问 https://hdoujin.org 并完成 Turnstile 验证
    2. 从浏览器的 localStorage 中提取 'clearance' 值
    3. 将该值传递给需要 clearance 参数的 API 函数
    """
    session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
        delay=5
    )
    session.headers.update({
        'Accept': 'application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br',
        'DNT': '1',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': _user_agent
    })
    return session


# 全局 session 实例（支持连接复用和 Cloudflare bypass）
_session = None


def _get_session() -> cloudscraper.CloudScraper:
    """获取或创建全局 session"""
    global _session
    if _session is None:
        _session = _create_session()
    return _session


def _make_headers(session_token: Optional[str] = None, full_browser: bool = False) -> Dict[str, str]:
    """
    创建 API 请求头

    Args:
        session_token: 会话令牌
        full_browser: 是否使用完整浏览器 headers（POST 请求必需，绕过 Cloudflare）
    """
    if full_browser:
        # 完整浏览器 headers - 必需用于 books_extra POST
        headers = {
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh,zh-CN;q=0.9,en;q=0.8",
            "DNT": "1",
            "Origin": "https://hdoujin.org",
            "Priority": "u=1, i",
            "Referer": "https://hdoujin.org/",
            "Sec-CH-UA": '"Microsoft Edge";v="141", "Not?A_Brand";v="8", "Chromium";v="141"',
            "Sec-CH-UA-Mobile": "?0",
            "Sec-CH-UA-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
            "User-Agent": _user_agent,
            "Content-Type": "application/json; charset=UTF-8"
        }
    else:
        # 简化 headers（GET 请求用）
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json; charset=UTF-8",
            "Referer": "https://hdoujin.org/",
            "Origin": "https://hdoujin.org",
            "User-Agent": _user_agent,
        }
    if session_token:
        headers["Authorization"] = f"Bearer {session_token}"
    return headers


def _handle_response(resp: cloudscraper.requests.Response) -> Dict[str, Any]:
    result: Dict[str, Any] = {"code": resp.status_code}
    ct = resp.headers.get("Content-Type", "")
    if resp.status_code <= 201:
        if ct and "application/json" in ct:
            try:
                result["body"] = resp.json()
            except Exception:
                result["body"] = resp.text
        else:
            result["body"] = resp.text
    else:
        # error
        try:
            result["error"] = resp.json()
        except Exception:
            result["error"] = resp.text
    return result


def _wrap_search_term(term: str, has_namespace: bool = False) -> str:
    """
    包装搜索词以匹配 JavaScript 的格式化规则

    JavaScript 实现：
    String.prototype.wrap = function(e) {
        if (e) {  // 如果有命名空间（如 "uploader:xxx"）
            const e = this.split(":");
            return `${e[0]}:${e.slice(1).join(":").wrap()}`
        }
        return (/\\s|\\+/g.test(this) ? `"^${this}$"` : `^${this}$`).toLowerCase()
    }

    规则：
    - 如果包含空格或+，用引号包裹：`"^term$"`
    - 否则直接用 ^$ 包裹：`^term$`
    - 转换为小写
    - 如果有命名空间前缀（如 uploader:），保持前缀，只处理后面的部分

    Args:
        term: 搜索词
        has_namespace: 是否包含命名空间前缀（如 "uploader:xxx"）

    Returns:
        格式化后的搜索词

    Examples:
        _wrap_search_term("test") -> "^test$"
        _wrap_search_term("test name") -> "^"test name"$"
        _wrap_search_term("uploader:artist", True) -> "uploader:^artist$"
    """
    if has_namespace and ":" in term:
        parts = term.split(":", 1)
        prefix = parts[0]
        value = parts[1] if len(parts) > 1 else ""
        wrapped_value = _wrap_search_term(value, False)
        return f"{prefix}:{wrapped_value}"

    # 检查是否包含空格或+
    if " " in term or "+" in term:
        return f'"^{term}$"'.lower()
    else:
        return f"^{term}$".lower()


# ---- Auth endpoints (Kn) ----
def login(payload: Dict[str, Any], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{AUTH_BASE}/login?crt={clearance}"
    headers = _make_headers(full_browser=True)
    session = _get_session()
    resp = session.post(url, headers=headers, json=payload, timeout=timeout)
    return _handle_response(resp)


def register(payload: Dict[str, Any], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{AUTH_BASE}/register?crt={clearance}"
    headers = _make_headers(full_browser=True)
    session = _get_session()
    resp = session.post(url, headers=headers, json=payload, timeout=timeout)
    return _handle_response(resp)


def logout(session_token: str, clearance: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    # JS appends crt via Qn wrapper for logout; accept optional clearance
    crt = f"?crt={clearance}" if clearance else ""
    url = f"{AUTH_BASE}/logout{crt}"
    headers = _make_headers(session_token, full_browser=True)
    session = _get_session()
    resp = session.post(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def auth_check(session_token: str, timeout: int = 30) -> Dict[str, Any]:
    """
    验证 session token 并获取用户信息

    Args:
        session_token: 当前的会话令牌
        timeout: 超时时间

    Returns:
        成功: {"code": 200, "body": {"username": "...", "role": 1, ...}}
        失败: {"code": 401, ...}  # session token 无效或过期
    """
    url = f"{AUTH_BASE}/check"
    headers = _make_headers(session_token, full_browser=True)
    session = _get_session()
    resp = session.post(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def auth_refresh(refresh_token: str, timeout: int = 30) -> Dict[str, Any]:
    """
    使用 refresh token 刷新获取新的 session token

    ⚠️ 重要：刷新只更新 session token，refresh token 本身保持不变！

    Token 管理逻辑：
    - 登录/注册返回：{"session": "...", "refresh": "...", "expr": timestamp}
    - 刷新请求返回：{"session": "new_session_token"}  # ⚠️ 只返回新 session

    客户端需要维护的完整 token 结构：
    {
        "refresh": "long_lived_refresh_token",  # 长期有效（登录时获取，保持不变）
        "session": "short_lived_session_token", # 短期有效（定期刷新更新）
        "expr": 1234567890,                     # refresh token 过期时间戳（秒）
        "next": 1234567890                      # 下次刷新时间戳（毫秒）
    }

    刷新流程：
    1. 使用同一个 refresh_token 请求刷新
    2. 服务器返回新的 session_token
    3. 客户端更新 tokens["session"]，但保持 tokens["refresh"] 不变
    4. 设置新的 tokens["next"] = 当前时间 + 24小时
    5. 重复此过程，直到 refresh_token 过期（达到 expr 时间）

    使用示例：
        # 1. 登录获取初始 tokens
        login_result = login({"username": "...", "password": "..."}, clearance)
        tokens = {
            "refresh": login_result["body"]["refresh"],  # 长期保持不变
            "session": login_result["body"]["session"],
            "expr": login_result["body"]["expr"],
            "next": time.time() * 1000 + 24 * 3600 * 1000
        }

        # 2. 定期刷新 session token（refresh token 不变）
        if time.time() * 1000 >= tokens["next"]:
            refresh_result = auth_refresh(tokens["refresh"])  # 使用同一个 refresh
            if refresh_result["code"] == 201:
                tokens["session"] = refresh_result["body"]["session"]  # 只更新 session
                tokens["next"] = time.time() * 1000 + 24 * 3600 * 1000
                # tokens["refresh"] 保持不变！

        # 3. 直到 refresh token 过期才需要重新登录
        if tokens["expr"] * 1000 <= time.time() * 1000:
            # refresh token 过期，需要重新登录
            login_result = login(...)
            tokens = {...}  # 获取新的 refresh 和 session

    Args:
        refresh_token: 长期有效的 refresh token（从登录时获取，保持不变）
        timeout: 超时时间

    Returns:
        成功: {"code": 201, "body": {"session": "new_session_token"}}
        失败: {"code": 401, "error": "..."}  # refresh token 过期或被撤销
    """
    url = f"{AUTH_BASE}/refresh"
    headers = _make_headers(refresh_token, full_browser=True)
    session = _get_session()
    resp = session.post(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def reset_password(payload: Dict[str, Any], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{AUTH_BASE}/reset?crt={clearance}"
    headers = _make_headers(full_browser=True)
    session = _get_session()
    resp = session.post(url, headers=headers, json=payload, timeout=timeout)
    return _handle_response(resp)


def create_reset(payload: Dict[str, Any], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{AUTH_BASE}/create_reset?crt={clearance}"
    headers = _make_headers(full_browser=True)
    session = _get_session()
    resp = session.post(url, headers=headers, json=payload, timeout=timeout)
    return _handle_response(resp)


# Clearance endpoints
def clearance_create(turnstile_token: str, timeout: int = 30) -> Dict[str, Any]:
    """
    使用 Cloudflare Turnstile 临时令牌创建 clearance token

    ⚠️ 警告：此函数需要 Turnstile 临时令牌，无法通过 Python 自动获取！

    获取 Turnstile 令牌的方法：
    1. 使用浏览器自动化工具（Selenium/Playwright）访问 hdoujin.org
    2. 等待 Turnstile 验证完成并从 callback 中提取临时令牌
    3. 将临时令牌传递给此函数

    或者更简单的方法：
    - 直接在浏览器中完成验证，从 localStorage 获取最终的 clearance token
    - 跳过此函数，直接使用 clearance token 调用其他 API

    Args:
        turnstile_token: Cloudflare Turnstile 验证完成后返回的临时令牌
        timeout: 超时时间

    Returns:
        {"code": 201, "body": "clearance_token_string"}
    """
    url = f"{AUTH_BASE}/clearance"
    headers = _make_headers(turnstile_token, full_browser=True)
    session = _get_session()
    resp = session.post(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def clearance_check(clearance_token: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    # JS used Qn GET and attached Authorization Bearer clearance token
    url = f"{AUTH_BASE}/clearance"
    headers = _make_headers(clearance_token)
    session = _get_session()
    resp = session.get(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


# ---- Books API (Xn) ----
def books_search(params: Dict[str, Any], session_token: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    搜索书籍

    Args:
        params: 搜索参数字典，支持以下参数：
            - s: 搜索关键词（需要用 _wrap_search_term() 包装）
            - lang: 语言过滤（位掩码，如 2=English）
            - include: 包含的标签 ID 列表（逗号分隔字符串）
            - exclude: 排除的标签 ID 列表（逗号分隔字符串）
            - page: 页码（从 1 开始）
            - sort: 排序方式（2=Title, 3=Pages, 4=Date, 7=Favorited, 8=Views, 9=Favorites）
        session_token: 可选的会话令牌（未登录用户可不提供）
        timeout: 超时时间

    Returns:
        搜索结果列表

    Note:
        - ✅ 无需 token 即可访问（公开 API）
        - 提供 session_token 可能返回更多信息（如收藏状态）

    JavaScript 搜索参数构建逻辑：
        1. 搜索词 (s) 需要用 wrap() 方法包装：
           - 简单词: "test" -> "^test$"
           - 带空格: "test name" -> '"^test name$"'
           - 命名空间: "uploader:artist" -> 'uploader:^artist$'

        2. 语言 (lang): 位掩码值（1=English, 2=Japanese, 4=Chinese, 8=Korean）

        3. 标签过滤 (include/exclude):
           - 从设置或 URL 参数读取
           - 以逗号分隔的标签 ID: "123,456,789"

        4. URL 参数自动添加 "?" 前缀（如果需要）

    Examples:
        # 1. 简单搜索
        params = {"s": _wrap_search_term("artist_name")}
        result = books_search(params)

        # 2. 带过滤的搜索
        params = {
            "s": _wrap_search_term("test"),
            "lang": "2",  # English only
            "page": "1"
        }

        # 3. 标签过滤
        params = {
            "include": "123,456",  # 包含这些标签
            "exclude": "789",      # 排除这些标签
            "sort": "4"            # 按日期排序
        }

        # 4. Uploader 搜索（命名空间搜索）
        params = {"s": _wrap_search_term("uploader:artistname", has_namespace=True)}
    """
    url = f"{API_BASE}/books"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.get(url, headers=headers, params=params, timeout=timeout)
    return _handle_response(resp)


def books_index(params: Dict[str, Any], session_token: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    浏览书籍索引

    Note:
        - ✅ 无需 token 即可访问（公开 API）
        - 提供 session_token 可能返回更多信息
    """
    url = f"{API_BASE}/books/index"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.get(url, headers=headers, params=params, timeout=timeout)
    return _handle_response(resp)


def books_popular(params: Dict[str, Any], session_token: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    获取热门书籍

    Note:
        - ✅ 无需 token 即可访问（公开 API）
        - 提供 session_token 可能返回更多信息
    """
    url = f"{API_BASE}/books/popular"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.get(url, headers=headers, params=params, timeout=timeout)
    return _handle_response(resp)


def books_random(session_token: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    获取随机书籍

    Note:
        - ✅ 无需 token 即可访问（公开 API）
    """
    url = f"{API_BASE}/books/random"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.get(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def books_get_detail(id_: str, key: str, session_token: Optional[str] = None, timeout: int = 30) -> Dict[str, Any]:
    """
    获取书籍详细信息

    Args:
        id_: 书籍 ID
        key: 书籍密钥
        session_token: 可选的会话令牌
        timeout: 超时时间

    Returns:
        书籍详细信息（标题、标签、页数等）

    Note:
        - ✅ 完全公开的 API，无需任何 token！
        - 这是唯一完全不需要 token 的详情接口
    """
    url = f"{API_BASE}/books/detail/{id_}/{key}"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.get(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def books_extra(id_: str, key: str, payload: Dict[str, Any], session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    """
    获取书籍的额外信息（包含不同分辨率的 data_id 和 data_key）

    根据实际测试验证：
    - 必须使用 POST 方法 + 完整浏览器 headers
    - URL: /books/detail/{id}/{key}?crt={clearance}
    - 成功返回: {data: {"0": {id, key, size}, "1280": {id, key, size}, "1920": {id, key, size}}}

    这些 data[resolution].id 和 data[resolution].key 用于后续的 books_read
    """
    url = f"{API_BASE}/books/detail/{id_}/{key}?crt={clearance}"
    headers = _make_headers(session_token, full_browser=True)
    session = _get_session()
    resp = session.post(url, headers=headers, json=payload, timeout=timeout)
    return _handle_response(resp)


def books_read(id_: str, key: str, resolution: str, session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    """
    读取指定分辨率的书籍内容（返回所有页面的 URL 列表）

    注意：需要先调用 books_extra 获取 data_id 和 data_key

    Args:
        id_: 书籍 ID
        key: 书籍密钥
        resolution: 分辨率 ("0"=原图, "1280", "1920")
        session_token: 会话令牌
        clearance: Cloudflare clearance token

    Returns:
        包含 base URL 和 entries 列表的字典:
        {
            "base": "https://erocdn.net/books/data/{data_id}/{data_key}/{hash}/{resolution}",
            "entries": [
                {"path": "/hash/uuid.png", "dimensions": [width, height]},
                ...
            ]
        }
    """
    # 1. 先获取 data_id 和 data_key
    extra = books_extra(id_, key, {}, session_token, clearance)

    if extra.get("code") != 200 or "body" not in extra:
        return extra  # 返回错误

    body = extra["body"]
    if "data" not in body or resolution not in body["data"]:
        return {"code": 400, "error": f"Resolution {resolution} not available"}

    data_info = body["data"][resolution]
    data_id = data_info["id"]
    data_key = data_info["key"]

    # 2. 构建 URL（最后参数是分辨率）
    url = f"{API_BASE}/books/data/{id_}/{key}/{data_id}/{data_key}/{resolution}?crt={clearance}"
    headers = _make_headers(session_token, full_browser=True)
    session = _get_session()
    resp = session.get(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def books_download(id_: str, key: str, resolution: str, session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    """
    获取书籍下载链接（POST 请求，返回 CDN 下载 URL）

    类似: POST /books/data/{id}/{key}/{data_id}/{data_key}/{resolution}?action=dl&crt={clearance}
    返回: 下载链接 URL（如 https://erocdn.net/books/download/...）

    Args:
        id_: 书籍 ID
        key: 书籍密钥
        resolution: 分辨率 ("0"=原图, "1280", "1920")
        session_token: 会话令牌
        clearance: Cloudflare clearance token

    Returns:
        {"code": 200, "body": { "base": "https://erocdn.net/books/download/..." } }
    """
    # 1. 先获取 data_id 和 data_key
    extra = books_extra(id_, key, {}, session_token, clearance)

    if extra.get("code") != 200 or "body" not in extra:
        return extra  # 返回错误

    body = extra["body"]
    if "data" not in body or resolution not in body["data"]:
        return {"code": 400, "error": f"Resolution {resolution} not available"}

    data_info = body["data"][resolution]
    data_id = data_info["id"]
    data_key = data_info["key"]

    # 2. 构建下载 URL（带 action=dl 参数）
    url = f"{API_BASE}/books/data/{id_}/{key}/{data_id}/{data_key}/{resolution}?action=dl&crt={clearance}"
    headers = _make_headers(session_token, full_browser=True)
    session = _get_session()

    # 使用 POST 请求
    resp = session.post(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def books_download_page(base_url: str, page_path: str, timeout: int = 30) -> bytes:
    """
    下载单页图片（从 books_read 返回的 URL）

    Args:
        base_url: 从 books_read 获取的 base URL
        page_path: 从 books_read entries 获取的 path
        timeout: 超时时间

    Returns:
        图片的二进制数据

    Example:
        result = books_read(id, key, "1280", session, clearance)
        base = result["body"]["base"]
        for entry in result["body"]["entries"]:
            image_data = books_download_page(base, entry["path"])
    """
    url = base_url + page_path
    session = _get_session()
    headers = _make_headers(full_browser=True)
    resp = session.get(url, headers=headers, timeout=timeout, stream=True)

    if resp.status_code == 200:
        return resp.content
    else:
        raise Exception(f"Download failed: {resp.status_code}")


# Reports
def reports_search(params: Dict[str, Any], session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    params = dict(params)
    params["crt"] = clearance
    url = f"{API_BASE}/books/reports"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.get(url, headers=headers, params=params, timeout=timeout)
    return _handle_response(resp)


def report_create(id_: str, key: str, payload: Dict[str, Any], session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{API_BASE}/books/report/{id_}/{key}?crt={clearance}"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.post(url, headers=headers, json=payload, timeout=timeout)
    return _handle_response(resp)


def report_review(id_: str, session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{API_BASE}/books/reports/{id_}/review?crt={clearance}"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.post(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def report_delete(id_: str, session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{API_BASE}/books/reports/{id_}?crt={clearance}"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.delete(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


# Tags
def tags(namespace: int = 0, sum_: bool = False, timeout: int = 30) -> Dict[str, Any]:
    """
    获取标签列表

    Args:
        namespace: 命名空间过滤（0=全部）
        sum_: 是否包含统计信息
        timeout: 超时时间

    Returns:
        标签列表

    Note:
        - ✅ 完全公开的 API，无需任何 token！
    """
    params = {}
    if namespace:
        params["namespace"] = namespace
    if sum_:
        params["sum"] = "true"
    url = f"{API_BASE}/books/tags"
    session = _get_session()
    resp = session.get(url, params=params, timeout=timeout)
    return _handle_response(resp)


def tags_filters(timeout: int = 30) -> Dict[str, Any]:
    """
    获取标签过滤器配置

    Note:
        - ✅ 完全公开的 API，无需任何 token！
    """
    url = f"{API_BASE}/books/tags/filters"
    session = _get_session()
    resp = session.get(url, timeout=timeout)
    return _handle_response(resp)


# Favorites
def favorites_search(params: Dict[str, Any], session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    params = dict(params)
    params["crt"] = clearance
    url = f"{API_BASE}/books/favorites"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.get(url, headers=headers, params=params, timeout=timeout)
    return _handle_response(resp)


def favorite_add(id_: str, key: str, session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{API_BASE}/books/favorites/{id_}/{key}?crt={clearance}"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.post(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


def favorite_delete(id_: str, key: str, session_token: Optional[str], clearance: str, timeout: int = 30) -> Dict[str, Any]:
    url = f"{API_BASE}/books/favorites/{id_}/{key}?crt={clearance}"
    headers = _make_headers(session_token)
    session = _get_session()
    resp = session.delete(url, headers=headers, timeout=timeout)
    return _handle_response(resp)


if __name__ == "__main__":
    # Quick smoke example (no real tokens provided) - user should replace placeholders
    print("hdoujin_api module loaded. Use functions programmatically. See README.md for examples.")
