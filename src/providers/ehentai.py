import re, os, json, time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

from utils import check_dirs

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

def get_original_tag(text):
    dictpath = check_dirs(os.path.join('data', 'ehentai', 'translations'))
    tags_json_path = os.path.join(dictpath, 'tags.json')
    if os.path.isfile(tags_json_path):
        with open(tags_json_path, 'r', encoding='utf-8') as rf:
            tagsdict = json.load(rf)
    else:
        tagsdict = {}
    if text in tagsdict:
        return tagsdict[text]
    else:
        print('未找到词条,搜索在线内容')
        url = 'https://ehwiki.org/wiki/' + text.replace(' ','_')
        response = requests.get(url, headers=headers)
        searchJapanese = re.search(r'Japanese</b>:\s*(.+?)<', response.text)
        if not searchJapanese == None:
            tagsdict[text] = re.sub(' ','',searchJapanese.group(1))
            with open(tags_json_path, 'w', encoding='utf-8') as wf:
                json.dump(tagsdict, wf, ensure_ascii=False, indent=4)
            return tagsdict[text]

def male_only_taglist():
    data_dir = check_dirs(os.path.join("data", "ehentai"))
    json_path = os.path.join(data_dir, "tags", "male_only_taglist.json")
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)['content']
    m_list = []
    
    fetish_html_path = os.path.join(data_dir, "fetish_listing.html")
    if not os.path.exists(fetish_html_path):
        url = "https://ehwiki.org/wiki/Fetish_Listing"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            with open(fetish_html_path, 'w') as f:
                f.write(response.text)
    
    with open(fetish_html_path) as f:
        soup = BeautifulSoup(f, 'html.parser')
        # 查找所有带有 "♂" 的 <a> 标签
        for a_tag in soup.find_all('a'):
            # 检查<a>标签后是否有 ♂
            if a_tag.next_sibling and "♂" in a_tag.next_sibling:
                m_list.append(a_tag.string.strip('\u200e'))
    with open(json_path, 'w') as j:
        json.dump({"content" : m_list}, j, indent=4)
    return m_list

class EHentaiTools:
    def __init__(self, cookie, logger=None):
        self.cookie = cookie
        self.logger = logger
        self.session = requests.Session()
        self.session.headers.update(headers)
        self.session.cookies.update(cookie)
        self.favcat_map = {}
    
    def _normalize_time(self, time_str: str) -> str:
        """
        标准化时间字符串为ISO 8601格式，便于可靠比较
        如果无法解析，返回原字符串并记录警告
        """
        if not time_str or not isinstance(time_str, str):
            return ""
        
        time_str = time_str.strip()
        
        # 已经是标准格式，直接返回
        if re.match(r'^\d{4}-\d{2}-\d{2}( \d{2}:\d{2})?$', time_str):
            return time_str
        
        # 尝试解析其他可能的格式
        try:
            # 尝试常见格式
            for fmt in ["%Y-%m-%d %H:%M", "%Y-%m-%d", "%d %b %Y", "%b %d, %Y"]:
                try:
                    dt = datetime.strptime(time_str, fmt)
                    return dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    continue
        except Exception as e:
            if self.logger:
                self.logger.warning(f"无法标准化时间字符串 '{time_str}': {e}")
        
        # 无法解析，返回原字符串
        return time_str

    def _check_url(self, url, name, error_msg, success_msg, keyword=None):
        try:
            response = self.session.get(url, allow_redirects=True, timeout=10)
            final_url = response.url.lower()
            valid = True
            eh_funds = None
            if 'login' in final_url or (keyword and keyword not in final_url):
                valid = False
                if self.logger:
                    self.logger.error(error_msg)
            else:
                if name == "E-Hentai":
                    eh_funds = self.get_funds(response.text)
                if self.logger:
                    self.logger.info(success_msg)
            return valid, eh_funds
        except Exception as e:
            if self.logger:
                self.logger.warning(f"无法打开 {url}, 请检查网络: {e}")
            return None, None

    def is_valid_cookie(self):
        # 先检查 E-Hentai
        eh_valid, eh_funds = self._check_url(
            "https://e-hentai.org/home.php",
            "E-Hentai",
            "无法访问 https://e-hentai.org/home.php, Archive 下载功能将不可用",
            "成功访问 https://e-hentai.org/home.php, Archive 下载功能可用"
        )
        # 再检查 ExHentai
        exh_valid, _ = self._check_url(
            "https://exhentai.org/uconfig.php",
            "ExHentai",
            "无法访问 https://exhentai.org/uconfig.php, ExHentai 下载可能受限",
            "成功访问 https://exhentai.org/uconfig.php, ExHentai 下载功能可用",
            keyword="uconfig"
        )

        return eh_valid, exh_valid, eh_funds

    def get_funds(self, html_text):
        soup = BeautifulSoup(html_text, 'html.parser')
        h2_tag = soup.find('h2', string='Total GP Gained')
        if h2_tag:
            homebox_div = h2_tag.find_next_sibling('div', class_='homebox')
            if homebox_div:
                table = homebox_div.find('table')
                if table:
                    total_gp = 0
                    # 遍历表格中的每一行
                    for row in table.find_all('tr'):
                        # GP 数值通常在每行的第一个 <td> 标签中
                        td = row.find('td')
                        if td:
                            gp_text = td.get_text(strip=True)
                            if gp_text:
                                try:
                                    # 移除逗号并转换为整数
                                    total_gp += int(gp_text.replace(',', ''))
                                except ValueError:
                                    # 如果转换失败，可能不是数字，记录警告并跳过
                                    if self.logger:
                                        self.logger.warning(f"无法从 '{gp_text}' 中解析 GP 数值")
                    return total_gp
        return None

    # 从 E-Hentai API 获取画廊信息
    def get_gmetadata(self, url):
        API = 'https://api.e-hentai.org/api.php'
        searchUrl = re.search(r'g\/(\d+?)\/(.+?)(\/|$)', url)
        if not searchUrl == None:
            gid = searchUrl.group(1)
            gtoken = searchUrl.group(2)
            data = {
                "method": "gdata",
                "gidlist": [
                    [gid,gtoken]
                ],
                "namespace": 1
                }
            response = self.session.post(API,json=data)
            if response.status_code == 200:
                if self.logger: self.logger.info(response.json())
                gmetadata_dir = check_dirs(os.path.join('data', 'ehentai', 'gmetadata'))
                with open(os.path.join(gmetadata_dir, f'{gid}.json'), 'w+', encoding='utf-8') as wf:
                    json.dump(response.json(),wf,ensure_ascii=False,indent=4)
                return response.json()['gmetadata'][0]
        else:
            if self.logger: self.logger.error(f'解析{url}时遇到了错误')

    def _download(self, url, path, task_id=None, tasks=None, tasks_lock=None):
        try:
            with self.session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0

                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        # 检查任务是否被取消
                        if task_id and tasks and tasks_lock:
                            with tasks_lock:
                                task = tasks.get(task_id)
                                if task and task.cancelled:
                                    if self.logger:
                                        self.logger.info(f"任务 {task_id} 被用户取消，正在清理文件")
                                    # 删除已下载的文件
                                    if os.path.exists(path):
                                        os.remove(path)
                                    # 返回None而不是抛出异常，避免中断线程
                                    return None

                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)

                            # 更新进度信息
                            if task_id and tasks and tasks_lock:
                                progress = 0
                                if total_size > 0:
                                    progress = min(100, int((downloaded / total_size) * 100))

                                with tasks_lock:
                                    if task_id in tasks:
                                        tasks[task_id].progress = progress
                                        tasks[task_id].downloaded = downloaded
                                        tasks[task_id].total_size = total_size
                                        # 直接下载模式无法获取实时速度，设置为0
                                        tasks[task_id].speed = 0
                if self.logger:
                    self.logger.info(f"下载完成: {path}")
                print(f"下载完成: {path}")
                return path
        except Exception as e:
            if self.logger:
                self.logger.error(f"下载失败: {e}")
            return None
        
    def _download_torrent(self, torrent_url, torrent_name):
        try:
            if self.logger: self.logger.info(f"尝试下载种子: {torrent_url}")
            response = self.session.get(torrent_url, timeout=10)
            
            # 即使 gid 错误, ehtracker 也会返回 200, 但内容是 HTML。
            # 因此需要通过 Content-Type 来判断是否是真正的种子文件。
            content_type = response.headers.get('Content-Type', '').lower()
            if response.status_code == 200 and 'text/html' not in content_type:
                torrents_dir = check_dirs(os.path.join('.', 'data', 'ehentai', 'torrents'))
                torrent_path = os.path.join(torrents_dir, torrent_name)
                with open(torrent_path, 'wb') as f:
                    f.write(response.content)
                
                # 在文件系统层面验证文件是否有效
                if os.path.isfile(torrent_path) and os.path.getsize(torrent_path) > 0:
                    if self.logger: self.logger.info(f"种子下载并验证成功: {torrent_path}")
                    return torrent_path
                else:
                    if self.logger: self.logger.warning(f"种子文件写入失败或为空: {torrent_path}")
                    return None
            else:
                if self.logger:
                    self.logger.warning(f"下载种子失败(gid可能无效): {torrent_url}, status: {response.status_code}, content-type: {content_type}")
                return None
        except requests.RequestException as e:
            if self.logger: self.logger.error(f"下载种子时发生网络错误: {torrent_url}, error: {e}")
            return None

    def get_deleted_gallery_torrent(self, gmetadata):
        if not (gmetadata and gmetadata.get('torrents')):
            return
        torrents_list = gmetadata['torrents']
        if not torrents_list:
            if self.logger: self.logger.info("该画廊没有可用的种子文件。")
            return

        # 从最新到最旧排序种子, 优先尝试最新的
        sorted_torrents = sorted(torrents_list, key=lambda t: int(t.get('added', '0')), reverse=True)
        
        # 准备要尝试的 gids, 保持顺序
        ordered_gids = [
            gmetadata.get('gid'),
            gmetadata.get('parent_gid'),
            gmetadata.get('first_gid')
        ]
        valid_gids = [gid for gid in ordered_gids if gid is not None]

        torrent_path = None
        # 外层循环: 遍历所有种子 (从新到旧)
        for torrent in sorted_torrents:
            torrent_hash = torrent.get('hash')
            torrent_name = torrent.get('name')

            if not (torrent_hash and torrent_name):
                continue # 跳过无效的种子条目

            # 内层循环: 遍历所有有效的 gid
            for gid in valid_gids:
                torrent_url = f'https://ehtracker.org/get/{gid}/{torrent_hash}.torrent'
                torrent_path = self._download_torrent(torrent_url=torrent_url, torrent_name=torrent_name)
                if torrent_path:
                    if self.logger:
                        self.logger.info(f"成功下载种子: 使用 gid={gid} 和 hash={torrent_hash}")
                    break  # 成功, 退出内层循环
                
                # 为避免对服务器造成过大压力, 在每次失败的尝试后增加1秒延迟
                time.sleep(1)
            
            if torrent_path:
                return torrent_path
        
        if not torrent_path and self.logger:
            self.logger.warning(f"尝试了 {len(sorted_torrents)} 个种子和 {len(valid_gids)} 个gids, 仍未找到可用的种子文件。")

    def get_download_link(self, url, mode):
        response = self.session.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 检查是否有内容警告
            h1 = soup.find('h1')
            if h1 and h1.text == 'Content Warning':
                if self.logger: self.logger.info("检测到内容警告, 选择忽略并尝试重新加载")
                response = self.session.get(url + '/?nw=always')
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                else:
                    if self.logger: self.logger.error("添加 'nw=always' 参数后请求失败，请仔细联系脚本维护者排查问题")
                    return None, None
            # 先看看 Torrent 情况
            if not mode == 'archive':
                torrent_a_tag = soup.find("a", string=lambda text: text and "Torrent Download" in text,onclick=True)
                # 提取链接
                if torrent_a_tag:
                    # 可直接通过 torrent_a_tag.text 中的数字判断是否有种子
                    # 获取onclick属性中的URL
                    onclick_value = torrent_a_tag['onclick']
                    search_number = re.search(r'(\d+)', torrent_a_tag.text)
                    if not search_number == None: torrent_count = int(search_number.group(1))
                    if self.logger: self.logger.info(f"找到 {torrent_count} 个种子")
                    if torrent_count > 0:
                        # 提取URL
                        start_idx = onclick_value.find("'") + 1
                        end_idx = onclick_value.find("'", start_idx)
                        torrent_window_url = onclick_value[start_idx:end_idx]
                        torrent_list = {}
                        # 请求 torrent_list_url
                        response = self.session.get(torrent_window_url)
                        if response.status_code == 200:
                            text = response.text
                            search_outdated_text = re.search(r'(.+)<p.+Outdated Torrent', text, re.S)
                            if not search_outdated_text == None:
                                if self.logger: self.logger.info('发现 Outdated Torrent')
                                t_html = search_outdated_text.group(1)
                            else: t_html = text
                            t_soup = BeautifulSoup(t_html, 'html.parser')
                            form_list = t_soup.find_all('form', method="post")
                            torrent_list = []
                            for form in form_list:
                                for td in form.find_all('td'):
                                    a_tags_with_onclick = form.find('a', onclick=True)
                                    if a_tags_with_onclick:
                                        torrent_name = a_tags_with_onclick.text + '.torrent'
                                        torrent_link = a_tags_with_onclick['href']
                                    for span in td.find_all('span'):
                                        if 'Seeds' in td.text:
                                            seeds_count = re.search(r'(\d+)', td.text).group(1)
                                torrent_list.append({'name':torrent_name, 'link':torrent_link, 'count':int(seeds_count)})
                            # 边缘情况处理: 检查 torrent_list 是否为空以防止 ValueError
                            if torrent_list:
                                # 可读性改进: lambda 中使用更具描述性的变量名 `torrent`
                                # 最佳实践: .get() 方法可以安全地处理缺少 'count' 键的情况
                                max_seeds_torrent = max(torrent_list, key=lambda torrent: torrent.get('count', 0))
                                if self.logger: self.logger.info(f"共找到{len(torrent_list)}个有效种子, 本次选择, {max_seeds_torrent}")
                                
                                # 将种子下载至本地
                                torrent_path = self._download_torrent(torrent_url=max_seeds_torrent['link'], torrent_name=max_seeds_torrent['name'])
                                # 再将种子推送到 aria2, 种子将会下载到 dir
                                return 'torrent', torrent_path
                            else:
                                if self.logger: self.logger.warning("未找到任何有效种子。")
                # 获取 Archive
                if self.logger: self.logger.info('\n开始进行 Archive Download')
                archive_a_tag = soup.find("a", string="Archive Download",onclick=True)
                # 提取链接
                if archive_a_tag:
                    # 获取onclick属性中的URL
                    onclick_value = archive_a_tag['onclick']
                    # 提取URL
                    start_idx = onclick_value.find("'") + 1
                    end_idx = onclick_value.find("'", start_idx)
                    download_url = onclick_value[start_idx:end_idx]
                    if self.logger: self.logger.info(f"Archive Download Link: {download_url}")
                else:
                    if self.logger: self.logger.info("No matching element found.")
                data = {
                    "dltype":"org",
                    "dlcheck":"Download Original Archive"
                }
                try:
                    response = self.session.post(download_url, data)
                    a_soup = BeautifulSoup(response.text, 'html.parser')
                    # 查找所有带有 onclick 属性的 <a> 标签
                    a_tags_with_onclick = a_soup.find_all('a', onclick=True)
                    # 提取 href 属性内容
                    hrefs = [a['href'] for a in a_tags_with_onclick]
                    base_url = hrefs[0].replace("?autostart=1", "")
                    final_url = base_url + '?start=1'
                    if self.logger: self.logger.info(f"开始下载: {final_url}")
                    # 返回种子地址
                    return 'archive', final_url
                except Exception as e:
                    # 如果发生了特定类型的异常，执行这里的代码
                    if self.logger: self.logger.info(f"An error occurred: {e}")

    LAYOUT_SELECTORS = {
        "thumbnail": 'div[class^="itg gld"]',
        "minimal": 'table[class^="itg gltm"]',
        "compact": 'table[class^="itg gltc"]',
        "extended": 'table[class^="itg glte"]',
    }

    def _get_layout(self, soup: BeautifulSoup) -> str:
        for layout, selector in self.LAYOUT_SELECTORS.items():
            if soup.select_one(selector):
                return layout

    def _build_favcat_map(self, soup: BeautifulSoup) -> dict:
        favcat_map = {}
        fav_elements = soup.select('div.nosel div.fp[onclick]')
        for element in fav_elements:
            name_div = element.select_one('div:nth-of-type(3)')
            if not name_div:
                continue
            category_name = name_div.get_text(strip=True)
            onclick_attr = element.get('onclick', '')
            match = re.search(r"favcat=(\d+)", onclick_attr)
            if match:
                favcat_id = match.group(1)
                favcat_map[favcat_id] = category_name
        
        if favcat_map:
            # 使用 update 保留旧数据，以防页面不完整
            self.favcat_map.update(favcat_map)

        return favcat_map

    def _extract_thumbnail_galleries(self, soup: BeautifulSoup) -> list:
        galleries = []
        gallery_elements = soup.select('div.gl1t')
        for gallery in gallery_elements:
            info = {}
            title_element = gallery.select_one('a > span.glink')
            if title_element:
                info['title'] = title_element.get_text(strip=True)
                info['url'] = title_element.parent['href']
            thumb_element = gallery.select_one('div.gl3t img')
            if thumb_element:
                info['thumbnail_url'] = thumb_element['src']
            gl5t_divs = gallery.select('div.gl5t > div > div')
            for div in gl5t_divs:
                if 'cs' in div.get('class', []):
                    info['category'] = div.get_text(strip=True)
                elif div.get('id', '').startswith('posted_'):
                    time_text = div.get_text(strip=True)
                    info['posted_date'] = time_text
                    info['favcat_title'] = div.get('title', '')
                    info['added'] = self._normalize_time(time_text)
                elif 'pages' in div.get_text(strip=True):
                    info['pages'] = div.get_text(strip=True)
            tags = gallery.select('div.gl6t > div.gt')
            info['tags'] = [tag.get('title', '') for tag in tags]
            if info:
                galleries.append(info)
        return galleries

    def _extract_minimal_galleries(self, soup: BeautifulSoup) -> list:
        galleries = []
        gallery_elements = soup.select('table[class^="itg gltm"] tr')
        for row in gallery_elements:
            if not row.find('td', class_='gl1m'):
                continue
            info = {}
            title_element = row.select_one('td.gl3m a > div.glink')
            if title_element:
                info['title'] = title_element.get_text(strip=True)
                info['url'] = title_element.parent['href']
            thumb_element = row.select_one('div.glthumb img')
            if thumb_element:
                info['thumbnail_url'] = thumb_element.get('data-src') or thumb_element.get('src')
            category_element = row.select_one('td.gl1m.glcat > div.cs')
            if category_element:
                info['category'] = category_element.get_text(strip=True)
            posted_element = row.select_one('td.gl2m > div[id^="posted_"]')
            if posted_element:
                time_text = posted_element.get_text(strip=True)
                info['posted_date'] = time_text
                info['favcat_title'] = posted_element.get('title', '')
                info['added'] = self._normalize_time(time_text)
            tags = row.select('div.gltm > div.gt')
            info['tags'] = [tag.get('title', '') for tag in tags]
            if info:
                galleries.append(info)
        return galleries

    def _extract_compact_galleries(self, soup: BeautifulSoup) -> list:
        galleries = []
        gallery_elements = soup.select('table[class^="itg gltc"] tr')
        for row in gallery_elements:
            if not row.find('td', class_='gl1c'):
                continue
            info = {}
            title_element = row.select_one('td.gl3c a > div.glink')
            if title_element:
                info['title'] = title_element.get_text(strip=True)
                info['url'] = title_element.parent['href']
            thumb_element = row.select_one('div.glthumb img')
            if thumb_element:
                info['thumbnail_url'] = thumb_element.get('data-src') or thumb_element.get('src')
            category_element = row.select_one('td.gl1c.glcat > div.cn')
            if category_element:
                info['category'] = category_element.get_text(strip=True)
            posted_element = row.select_one('td.gl2c > div > div[id^="posted_"]')
            if posted_element:
                time_text = posted_element.get_text(strip=True)
                info['posted_date'] = time_text
                info['favcat_title'] = posted_element.get('title', '')
                info['added'] = self._normalize_time(time_text)
            tags = row.select('td.gl3c.glname div.gt')
            info['tags'] = [tag.get('title', '') for tag in tags]
            authors = [tag.text for tag in tags if tag.get('title', '').startswith('artist:')]
            if authors:
                info['author'] = ' / '.join(authors)
            if info:
                galleries.append(info)
        return galleries

    def _extract_extended_galleries(self, soup: BeautifulSoup) -> list:
        galleries = []
        gallery_elements = soup.select('table[class^="itg glte"] tr')
        for row in gallery_elements:
            if not row.find('td', class_='gl1e'):
                continue
            info = {}
            link_element = row.select_one('td.gl1e a')
            if link_element:
                info['url'] = link_element['href']
                thumb_element = link_element.select_one('img')
                if thumb_element:
                    info['title'] = thumb_element.get('title', '')
                    info['thumbnail_url'] = thumb_element['src']
            category_element = row.select_one('div.gl3e div.cn')
            if category_element:
                info['category'] = category_element.get_text(strip=True)
            posted_element = row.select_one('div[id^="posted_"]')
            if posted_element:
                time_text = posted_element.get_text(strip=True)
                info['posted_date'] = time_text
                info['favcat_title'] = posted_element.get('title', '')
                info['added'] = self._normalize_time(time_text)
            tags = row.select('div.gl4e table div[title]')
            info['tags'] = [tag.get('title', '') for tag in tags]
            authors = [tag.text for tag in tags if tag.get('title', '').startswith('artist:')]
            if authors:
                info['author'] = ' / '.join(authors)
            if info:
                galleries.append(info)
        return galleries

    def _parse_favorites_page(self, soup: BeautifulSoup) -> tuple[str, list]:
        layout = self._get_layout(soup)
        self._build_favcat_map(soup)  # 更新收藏夹列表缓存
        galleries_data = []
        if layout == 'thumbnail':
            galleries_data = self._extract_thumbnail_galleries(soup)
        elif layout == 'minimal':
            galleries_data = self._extract_minimal_galleries(soup)
        elif layout == 'compact':
            galleries_data = self._extract_compact_galleries(soup)
        elif layout == 'extended':
            galleries_data = self._extract_extended_galleries(soup)

        # 从页面中提取每个画廊的 favcat
        # 创建收藏夹名称到ID的反向映射
        name_to_id = {name: fav_id for fav_id, name in self.favcat_map.items()}
        
        if galleries_data:
            for gallery in galleries_data:
                # favcat_title 存储的是收藏夹名称，如 "Common", "💕" 等
                # 通过名称反查 favcat ID
                favcat_name = gallery.get('favcat_title', '')
                if favcat_name and favcat_name in name_to_id:
                    gallery['favcat'] = name_to_id[favcat_name]
                else:
                    gallery['favcat'] = None
        return layout, galleries_data

    def get_favcat_list(self) -> list:
        """获取用户收藏夹列表, 如果缓存为空则主动获取"""
        if not self.favcat_map:
            if self.logger:
                self.logger.info("收藏夹缓存为空, 正在主动获取...")
            url = "https://exhentai.org/favorites.php"
            try:
                response = self.session.get(url, allow_redirects=True, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    # _build_favcat_map 会自动更新 self.favcat_map
                    self._build_favcat_map(soup)
                    if self.logger:
                        self.logger.info(f"成功获取并缓存了 {len(self.favcat_map)} 个收藏夹分类。")
                else:
                    if self.logger:
                        self.logger.error(f"获取收藏夹列表失败: status_code={response.status_code}")
            except requests.RequestException as e:
                if self.logger:
                    self.logger.error(f"获取收藏夹列表时发生网络错误: {e}")

        # 无论如何都从当前缓存返回
        # 转换成前端需要的格式 [{'id': k, 'name': 'k: v'}, ...]
        favcat_list = [
            {'id': k, 'name': f"{k}: {v}"}
            for k, v in self.favcat_map.items()
        ]
        
        if favcat_list:
            favcat_list.sort(key=lambda x: int(x['id']))
        return favcat_list

    def get_favorites(self, favcat_list: list, existing_gids: set = None, initial_scan_pages: int = 1) -> list:
        """
        获取收藏夹画廊列表
        
        Args:
            favcat_list: 要同步的收藏夹分类ID列表
            existing_gids: 数据库中已存在的GID集合，用于增量扫描
            initial_scan_pages: 首次扫描页数，0表示全量扫描，其他数字表示扫描指定页数
            
        Returns:
            画廊列表
        """
        all_galleries = []
        stop_scanning = False
        consecutive_matches = 0  # 连续匹配计数器
        MATCH_THRESHOLD = 5  # 固定连续匹配阈值
        
        # 判断扫描模式
        if existing_gids is None or len(existing_gids) == 0:
            if initial_scan_pages == 0:
                scan_mode = "full_scan"
                max_pages = None  # 无限制
                if self.logger:
                    self.logger.info("数据库为空，将进行全量扫描（所有页）")
            else:
                scan_mode = "initial_scan"
                max_pages = initial_scan_pages
                if self.logger:
                    self.logger.info(f"数据库为空，将扫描前 {initial_scan_pages} 页")
        elif len(existing_gids) < MATCH_THRESHOLD:
            if initial_scan_pages == 0:
                scan_mode = "full_scan"
                max_pages = None
                if self.logger:
                    self.logger.info(f"数据库中只有 {len(existing_gids)} 个记录（少于{MATCH_THRESHOLD}个），将进行全量扫描")
            else:
                scan_mode = "initial_scan"
                max_pages = initial_scan_pages
                if self.logger:
                    self.logger.info(f"数据库中只有 {len(existing_gids)} 个记录（少于{MATCH_THRESHOLD}个），将扫描前 {initial_scan_pages} 页")
        else:
            scan_mode = "incremental"
            max_pages = None  # 增量扫描不限制页数，由匹配阈值控制
            if self.logger:
                self.logger.info(f"数据库中有 {len(existing_gids)} 个记录，将进行增量扫描（连续匹配{MATCH_THRESHOLD}个时停止）")
        
        # 从收藏夹首页开始, 强制按收藏时间排序
        url = "https://exhentai.org/favorites.php?inline_set=fs_f"
        page_count = 0

        while url and not stop_scanning:
            page_count += 1
            if self.logger:
                self.logger.info(f"正在获取收藏夹页面 {page_count}: {url}")
            
            try:
                response = self.session.get(url, allow_redirects=True, timeout=10)
                if response.status_code != 200:
                    if self.logger:
                        self.logger.error(f"获取收藏夹页面失败: {url}, status_code: {response.status_code}")
                    break
                
                soup = BeautifulSoup(response.text, 'html.parser')
                # 从页面中提取画廊信息
                _, galleries_data = self._parse_favorites_page(soup)
                
                if galleries_data:
                    for gallery in galleries_data:
                        # 检查画廊是否属于指定的 favcat
                        if gallery.get('favcat') not in favcat_list:
                            continue
                        
                        # 提取 GID
                        from utils import parse_gallery_url
                        gid, _ = parse_gallery_url(gallery.get('url', ''))
                        
                        if scan_mode == "incremental" and existing_gids and gid:
                            # 增量扫描模式
                            if gid in existing_gids:
                                consecutive_matches += 1
                                if self.logger:
                                    self.logger.info(f"发现已存在的 GID {gid}，连续匹配计数: {consecutive_matches}/{MATCH_THRESHOLD}")
                                
                                # 达到阈值，停止扫描
                                if consecutive_matches >= MATCH_THRESHOLD:
                                    stop_scanning = True
                                    if self.logger:
                                        self.logger.info(f"连续匹配 {MATCH_THRESHOLD} 个已存在的 GID，停止增量扫描。")
                                    break
                            else:
                                # 遇到新画廊，重置计数器并添加
                                consecutive_matches = 0
                                all_galleries.append(gallery)
                        else:
                            # first_page 模式，直接添加
                            all_galleries.append(gallery)
                
                if stop_scanning:
                    break
                
                # initial_scan 模式：检查是否达到页数限制
                if scan_mode == "initial_scan" and max_pages is not None:
                    if page_count >= max_pages:
                        if self.logger:
                            self.logger.info(f"已扫描 {page_count} 页，达到配置的页数限制，停止扫描。")
                        break

                # 查找下一页链接
                next_link = soup.select_one('div.searchnav a#dnext')
                if next_link and next_link.get('href'):
                    url = next_link['href']
                    time.sleep(10) # 避免请求过于频繁
                else:
                    url = None # 没有下一页了

            except requests.RequestException as e:
                if self.logger:
                    self.logger.error(f"获取收藏夹页面时发生网络错误: {url}, error: {e}")
                break
        
        return all_galleries

    def add_to_favorites(self, gid: int, token: str, favcat: str = '1', note: str = '') -> bool:
        """将画廊添加到收藏夹"""
        url = f"https://e-hentai.org/gallerypopups.php?gid={gid}&t={token}&act=addfav"
        form_data = {
            "favcat": favcat,
            "apply": "Apply Changes",
            "favnote": note,
            "update": "1"
        }
        try:
            response = self.session.post(url, data=form_data, timeout=10)
            if response.status_code == 200:
                if self.logger:
                    self.logger.info(f"成功将 gid={gid} 添加到收藏夹 (favcat={favcat})")
                return True
            else:
                if self.logger:
                    self.logger.error(f"将 gid={gid} 添加到收藏夹失败: status_code={response.status_code}, response={response.text}")
                return False
        except requests.RequestException as e:
            if self.logger:
                self.logger.error(f"将 gid={gid} 添加到收藏夹时发生网络错误: {e}")
            return False

    def delete_from_favorites(self, gid: str) -> bool:
        """从收藏夹中删除画廊"""
        url = "https://e-hentai.org/favorites.php"
        form_data = {
            "ddact": "delete",
            "modifygids[]": str(gid)
        }
        try:
            response = self.session.post(url, data=form_data, timeout=10)
            if response.status_code == 200:
                if self.logger:
                    self.logger.info(f"成功从收藏夹中删除 gid={gid}")
                return True
            else:
                if self.logger:
                    self.logger.error(f"从收藏夹中删除 gid={gid} 失败: status_code={response.status_code}, response={response.text}")
                return False
        except requests.RequestException as e:
            if self.logger:
                self.logger.error(f"从收藏夹中删除 gid={gid} 时发生网络错误: {e}")
            return False