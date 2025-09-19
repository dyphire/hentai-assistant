import re, os, json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

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

    def _check_url(self, url, name, error_msg, success_msg, keyword=None):
        try:
            response = self.session.get(url, allow_redirects=True, timeout=10)
            final_url = response.url.lower()
            valid = True
            if 'login' in final_url or (keyword and keyword not in final_url):
                valid = False
                if self.logger:
                    self.logger.error(error_msg)
            else:
                if self.logger:
                    self.logger.info(success_msg)
            return valid
        except Exception as e:
            if self.logger:
                self.logger.warning(f"无法打开 {url}, 请检查网络: {e}")
            return False

    def is_valid_cookie(self):
        # 先检查 E-Hentai
        eh_valid = self._check_url(
            "https://e-hentai.org/home.php",
            "E-Hentai",
            "无法访问 https://e-hentai.org/home.php, Archive 下载功能将不可用",
            "成功访问 https://e-hentai.org/home.php, Archive 下载功能可用"
        )
        # 再检查 ExHentai
        exh_valid = self._check_url(
            "https://exhentai.org/uconfig.php",
            "ExHentai",
            "无法访问 https://exhentai.org/uconfig.php, ExHentai 下载可能受限",
            "成功访问 https://exhentai.org/uconfig.php, ExHentai 下载功能可用",
            keyword="uconfig"
        )

        return eh_valid, exh_valid

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
        eh_valid, exh_valid = self.is_valid_cookie()
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

    def archive_download(self, url, mode):
        eh_valid, exh_valid = self.is_valid_cookie()
        if exh_valid:
            url = url.replace("e-hentai.org", "exhentai.org")
        else:
            url = url.replace("exhentai.org", "e-hentai.org")
        response = self.session.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
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
                            max_seeds_torrent = max(torrent_list, key=lambda x: x.get('count', 0))
                            if self.logger: self.logger.info(f"共找到{len(torrent_list)}个有效种子, 本次选择, {max_seeds_torrent}")
                            # 将种子下载至本地
                            torrent = self.session.get(max_seeds_torrent['link'])
                            torrent_path = os.path.join(check_dirs('./data/ehentai/torrents'), max_seeds_torrent['name'])
                            with open(torrent_path, 'wb') as f:
                                if self.logger: self.logger.info(f"开始下载: {torrent_link} ==> {torrent_path}")
                                f.write(torrent.content)
                            # 再将种子推送到 aria2, 种子将会下载到 dir
                            return 'torrent', torrent_path
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

    def get_favorites(self, favcat=0, max_pages=None):
        """
        获取收藏夹内容，按收藏时间排序
        :param favcat: 收藏夹分类 (0-9)
        :param max_pages: 最大页数，None表示获取所有
        :return: 收藏夹列表，每个项目包含gid, token, title, added_time等
        """
        favorites = []
        page = 0

        while True:
            # 优先使用ExHentai，如果不可用则使用E-Hentai
            eh_valid, exh_valid = self.is_valid_cookie()
            if exh_valid:
                # 尝试不同的URL格式
                urls_to_try = [
                    f"https://exhentai.org/favorites.php?favcat={favcat}&inline_set=dm_l&page={page}",
                    f"https://exhentai.org/favorites.php?favcat={favcat}&inline_set=dm_m&page={page}",
                    f"https://exhentai.org/favorites.php?favcat={favcat}&page={page}",
                ]
            else:
                urls_to_try = [
                    f"https://e-hentai.org/favorites.php?favcat={favcat}&inline_set=dm_l&page={page}",
                    f"https://e-hentai.org/favorites.php?favcat={favcat}&inline_set=dm_m&page={page}",
                    f"https://e-hentai.org/favorites.php?favcat={favcat}&page={page}",
                ]

            response = None
            final_url = None

            for url in urls_to_try:
                try:
                    response = self.session.get(url, timeout=30)
                    final_url = response.url or url  # 获取重定向后的URL，如果为None则使用原始URL
                    if response.status_code == 200:
                        break
                except Exception as e:
                    continue

            if not response or response.status_code != 200:
                if self.logger:
                    self.logger.error("所有URL尝试都失败了")
                break

            url = final_url  # 使用最终的URL

            try:
                response = self.session.get(url, timeout=30)
                if response.status_code != 200:
                    if self.logger:
                        self.logger.error(f"获取收藏夹页面失败: {response.status_code}")
                    break

                soup = BeautifulSoup(response.text, 'html.parser')

                # 检查是否还有内容 - 使用表格结构
                table = soup.find('table', class_='itg')
                if not table:
                    if self.logger:
                        self.logger.info(f"第{page}页没有找到画廊表格，可能已到最后一页")
                    break

                # 获取表格中的所有行（跳过表头）
                rows = table.find_all('tr')[1:]  # 跳过表头行
                if not rows:
                    if self.logger:
                        self.logger.info(f"第{page}页没有找到画廊行")
                    break

                for row in rows:
                    try:
                        # 获取行中的所有单元格
                        cells = row.find_all('td')
                        if len(cells) < 4:
                            continue

                        # 第三个单元格包含标题和链接
                        title_cell = cells[2]  # 标题单元格
                        link = title_cell.find('a')
                        if not link:
                            continue

                        href = link.get('href', '')
                        match = re.search(r'/g/(\d+)/([a-z0-9]+)/?', href)
                        if not match:
                            continue

                        gid = int(match.group(1))
                        token = match.group(2)

                        # 提取标题
                        title = link.find('div', class_='glink')
                        if title:
                            title = title.text.strip()
                        else:
                            title = link.text.strip()

                        # 第四个单元格包含收藏时间
                        time_cell = cells[3]  # 时间单元格
                        added_time = None
                        time_text = time_cell.text.strip()
                        if time_text:
                            try:
                                # 解析格式如 "2025-09-15 19:34"
                                added_time = datetime.strptime(time_text, "%Y-%m-%d %H:%M")
                            except ValueError:
                                try:
                                    # 尝试处理没有冒号的格式，如 "2025-09-1519:34"
                                    if len(time_text) == 16 and time_text[10] != ' ':
                                        time_text = time_text[:10] + ' ' + time_text[10:12] + ':' + time_text[12:]
                                        added_time = datetime.strptime(time_text, "%Y-%m-%d %H:%M")
                                except ValueError:
                                    pass

                        # 第二个单元格包含缩略图
                        image_cell = cells[1]  # 图片单元格
                        img = image_cell.find('img')
                        if img:
                            # 优先使用data-src属性（真正的图片URL），如果没有则使用src属性
                            thumbnail = img.get('data-src') or img.get('src', '')
                        else:
                            thumbnail = ''

                        # 提取标签
                        tags = []
                        tag_divs = title_cell.find_all('div', class_='gt')
                        for tag_div in tag_divs:
                            tag_text = tag_div.text.strip()
                            if tag_text:
                                tags.append(tag_text)

                        gallery_info = {
                            'gid': gid,
                            'token': token,
                            'title': title,
                            'added_time': added_time.isoformat() if added_time else None,
                            'thumbnail': thumbnail,
                            'tags': tags,
                            'url': f"https://e-hentai.org/g/{gid}/{token}/"
                        }

                        favorites.append(gallery_info)

                    except Exception as e:
                        continue

                page += 1
                if max_pages and page >= max_pages:
                    break

                # 检查是否有下一页
                next_page_link = soup.find('a', string='>')
                if not next_page_link:
                    break

            except Exception as e:
                if self.logger:
                    self.logger.error(f"获取收藏夹页面失败: {e}")
                break

        # 按收藏时间排序（最新的在前）
        favorites.sort(key=lambda x: x['added_time'] or '', reverse=True)

        if self.logger:
            self.logger.info(f"获取到 {len(favorites)} 个收藏项")

        return favorites

    def _load_favorites_cache(self, favcat=0):
        """加载收藏夹缓存"""
        cache_path = check_dirs('data/ehentai/favorites/') + f'favcat_{favcat}.json'
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"加载收藏夹缓存失败: {e}")
        return {'favorites': [], 'last_update': None}

    def _save_favorites_cache(self, favorites, favcat=0):
        """保存收藏夹缓存"""
        cache_path = check_dirs('data/ehentai/favorites/') + f'favcat_{favcat}.json'
        cache_data = {
            'favorites': favorites,
            'last_update': datetime.now().isoformat()
        }
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            if self.logger:
                self.logger.info(f"保存收藏夹缓存: {len(favorites)} 项")
        except Exception as e:
            if self.logger:
                self.logger.error(f"保存收藏夹缓存失败: {e}")

    def update_favorites_incremental(self, favcat=0, max_pages=None):
        """
        增量更新收藏夹，只获取新的收藏项
        :param favcat: 收藏夹分类 (0-9)
        :param max_pages: 最大页数，None表示获取所有
        :return: 新增的收藏项列表
        """
        # 加载现有缓存
        cache = self._load_favorites_cache(favcat)
        existing_favorites = cache['favorites']
        last_update = cache['last_update']

        if self.logger:
            self.logger.info(f"加载现有收藏夹缓存: {len(existing_favorites)} 项")

        # 获取所有收藏夹（或指定页数）
        all_favorites = self.get_favorites(favcat, max_pages)

        # 找出新增的收藏项
        existing_gids = {fav['gid'] for fav in existing_favorites}
        new_favorites = []

        for fav in all_favorites:
            if fav['gid'] not in existing_gids:
                new_favorites.append(fav)
                existing_favorites.append(fav)
            else:
                # 更新现有项的时间等信息
                for i, existing in enumerate(existing_favorites):
                    if existing['gid'] == fav['gid']:
                        existing_favorites[i] = fav
                        break

        # 按收藏时间排序
        existing_favorites.sort(key=lambda x: x.get('added_time') or '', reverse=True)

        # 保存更新后的缓存
        self._save_favorites_cache(existing_favorites, favcat)

        if self.logger:
            self.logger.info(f"增量更新完成，新增 {len(new_favorites)} 项收藏")

        return new_favorites

    def get_favcat_names(self):
        """
        获取收藏夹分类名称
        :return: 收藏夹名称列表
        """
        # 优先使用ExHentai，如果不可用则使用E-Hentai
        eh_valid, exh_valid = self.is_valid_cookie()
        if exh_valid:
            url = "https://exhentai.org/favorites.php"
        else:
            url = "https://e-hentai.org/favorites.php"

        try:
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                # 如果获取失败，返回默认名称
                return [
                    'Favorite 0', 'Favorite 1', 'Favorite 2', 'Favorite 3', 'Favorite 4',
                    'Favorite 5', 'Favorite 6', 'Favorite 7', 'Favorite 8', 'Favorite 9'
                ]

            soup = BeautifulSoup(response.text, 'html.parser')

            # 查找收藏夹分类div
            favcat_divs = soup.find_all('div', class_='fp')

            favcat_names = []
            for div in favcat_divs:
                # 获取收藏夹名称 - 尝试多种方式
                name_div = None

                # 方法1: 查找title属性
                if div.get('title'):
                    name_div = div.get('title')
                else:
                    # 方法2: 查找内部div的title属性
                    inner_div = div.find('div', class_='i')
                    if inner_div and inner_div.get('title'):
                        name_div = inner_div.get('title')
                    else:
                        # 方法3: 查找文本内容
                        text_divs = div.find_all('div')
                        for td in text_divs:
                            if td.text.strip() and not td.text.strip().isdigit():
                                name_div = td.text.strip()
                                break

                if name_div:
                    favcat_names.append(name_div)

            # 如果获取到的名称不够10个，用默认名称填充
            default_names = [
                'Favorite 0', 'Favorite 1', 'Favorite 2', 'Favorite 3', 'Favorite 4',
                'Favorite 5', 'Favorite 6', 'Favorite 7', 'Favorite 8', 'Favorite 9'
            ]

            while len(favcat_names) < 10:
                favcat_names.append(default_names[len(favcat_names)])

            return favcat_names[:10]  # 只返回前10个

        except Exception as e:
            if self.logger:
                self.logger.warning(f"获取收藏夹名称失败: {e}")
            # 返回默认名称
            return [
                'Favorite 0', 'Favorite 1', 'Favorite 2', 'Favorite 3', 'Favorite 4',
                'Favorite 5', 'Favorite 6', 'Favorite 7', 'Favorite 8', 'Favorite 9'
            ]
