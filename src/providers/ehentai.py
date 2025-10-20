import re, os, json
import requests
from bs4 import BeautifulSoup

from utils import check_dirs

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

def get_original_tag(text):
    dictpath = check_dirs('data/ehentai/translations/')
    if os.path.isfile(dictpath + 'tags.json'):
        with open(dictpath + 'tags.json', 'r', encoding='utf-8') as rf:
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
            with open(check_dirs(dictpath) + 'tags.json', 'w', encoding='utf-8') as wf:
                json.dump(tagsdict, wf, ensure_ascii=False, indent=4)
            return tagsdict[text]

def male_only_taglist():
    json_path = os.path.join(check_dirs("data/ehentai/tags"), "male_only_taglist.json")
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)['content']
    m_list = []
    if not os.path.exists("data/ehentai/fetish_listing.html"):
        url = "https://ehwiki.org/wiki/Fetish_Listing"
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            with open("data/ehentai/fetish_listing.html", 'w') as f:
                f.write(response.text)
    with open("data/ehentai/fetish_listing.html") as f:
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
                with open(check_dirs('data/ehentai/gmetadata/') + '{gid}.json'.format(gid=gid), 'w+', encoding='utf-8') as wf:
                    json.dump(response.json(),wf,ensure_ascii=False,indent=4)
                return response.json()['gmetadata'][0]
        else:
            if self.logger: self.logger.error(f'解析{url}时遇到了错误')

    def _download(self, url, path, task_id=None, tasks=None, tasks_lock=None):
        eh_valid, exh_valid, _ = self.is_valid_cookie()
        if exh_valid:
            url = url.replace("e-hentai.org", "exhentai.org")
        else:
            url = url.replace("exhentai.org", "e-hentai.org")
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
                    if self.logger: self.logger.error("添加 'nw=always' 参数后请求失败，请仔细排查问题")
                    return None, None
            # 先看看 Torrent 情况
            if mode == "torrent" or mode == "both": # 下载种子需要开启 aria2
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
                                torrent = self.session.get(max_seeds_torrent['link'])
                                torrent_path = os.path.join(check_dirs('./data/ehentai/torrents'), max_seeds_torrent['name'])
                                with open(torrent_path, 'wb') as f:
                                    if self.logger: self.logger.info(f"开始下载: {max_seeds_torrent['link']} ==> {torrent_path}")
                                    f.write(torrent.content)
                                # 再将种子推送到 aria2, 种子将会下载到 dir
                                return 'torrent', torrent_path
                            else:
                                if self.logger: self.logger.warning("未找到任何有效种子。")
            if mode == "archive" or mode == "both":
                # 直接使用GP下载Archive
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
                    # 保存请求页面用于调试
                    # with open('data/ehentai/download.html', 'w+', encoding='utf-8') as f: f.write(response.text)
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
                    info['posted_date'] = div.get_text(strip=True)
                    info['favcat_title'] = div.get('title', '')
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
                info['posted_date'] = posted_element.get_text(strip=True)
                info['favcat_title'] = posted_element.get('title', '')
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
                info['posted_date'] = posted_element.get_text(strip=True)
                info['favcat_title'] = posted_element.get('title', '')
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
                info['posted_date'] = posted_element.get_text(strip=True)
                info['favcat_title'] = posted_element.get('title', '')
            tags = row.select('div.gl4e table div[title]')
            info['tags'] = [tag.get('title', '') for tag in tags]
            authors = [tag.text for tag in tags if tag.get('title', '').startswith('artist:')]
            if authors:
                info['author'] = ' / '.join(authors)
            if info:
                galleries.append(info)
        return galleries

    def _parse_favorites_page(self, soup: BeautifulSoup, favcat: str) -> tuple[str, list]:
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

        if galleries_data:
            for gallery in galleries_data:
                gallery['favcat'] = favcat # 直接使用传入的 favcat ID
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

    def get_favorites(self, favcat_list: list) -> list:
        all_galleries = []
        for favcat in favcat_list:
            page_num = 0
            while True:
                url = f"https://exhentai.org/favorites.php?favcat={favcat}&page={page_num}"
                if self.logger:
                    self.logger.info(f"正在获取收藏夹: favcat={favcat}, page={page_num}")
                
                response = self.session.get(url, allow_redirects=True, timeout=10)
                if response.status_code != 200:
                    if self.logger:
                        self.logger.error(f"获取收藏夹页面失败: {url}, status_code: {response.status_code}")
                    break
                
                soup = BeautifulSoup(response.text, 'html.parser')
                _, galleries_data = self._parse_favorites_page(soup, favcat)
                
                if galleries_data:
                    all_galleries.extend(galleries_data)
                
                # 检查是否有下一页
                # 通过查找指向下一页的 '>' 按钮来判断
                next_button = soup.select_one('a[onclick="return false"]')
                if not next_button or next_button.text != '>':
                    break
                
                page_num += 1
                
        return all_galleries

    def add_to_favorites(self, gid: int, token: str, favcat: str = '1', note: str = '') -> bool:
        """将画廊添加到收藏夹"""
        url = f"https://exhentai.org/gallerypopups.php?gid={gid}&t={token}&act=addfav"
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