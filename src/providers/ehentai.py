import re, os, json
import requests
from bs4 import BeautifulSoup

from utils import check_dirs
from providers import aria2

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

def parse_filename(text):
    # 去除所有括号内的内容,将清理后的文本作为标题
    title = re.sub(r'\[.*?\]|\(.*?\)', '', text).strip()
    print(f'从文件名{text}中解析到 Title:', title)
    # 匹配开头[]内的内容,在EH的命名规范中,它总是代表作者信息
    search_author = re.search(r'\[(.+?)\]', text)
    if not search_author == None:
        author = search_author.group(1)
        search_writer = re.search(r'(.+?)\s*\((.+?)\)', search_author.group(1))
        # 判断作者和画师
        if not search_writer == None: 
            writer = search_writer.group(1) # 同人志的情况下，把社团视为 writer
            penciller = search_writer.group(2) # 把该漫画的作者视为 penciller
        else:
            writer = penciller = search_author.group(1)
        # 有时候也会在作者信息中著名原著作者, 尝试去分离信息, 并将原著作者与社团共同视为 writer
        for s in [ '、', ',']:
            if s in penciller:
                writer = writer + ', ' + penciller.split(s)[0]
                print('\nWriter:', writer)
                penciller = penciller.split(s)[1]
                print('Penciller:', penciller)
        return title, writer, penciller

def get_original_tag(self, text):
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
        global headers
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
        global headers
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
        session = requests.Session()
        # 设置全局的 headers
        global headers
        session.headers.update(headers)
        session.cookies.update(self.cookie)
        self.session = session
        if logger: self.logger = logger
        else: self.logger = None
    
    def is_valid_cookie(self):
        try:
            response = self.session.get('https://e-hentai.org/home.php', allow_redirects=True, timeout=10)
            final_url = response.url
            if 'login' in final_url:
                if self.logger: self.logger.error("无法访问 https://e-hentai.org/home.php, Archive 下载功能将不可用")
                return False
            elif final_url == 'https://e-hentai.org/home.php':
                if self.logger: self.logger.info("成功访问 https://e-hentai.org/home.php, Archive 下载功能可用")
                return True
        except Exception as e:
            if self.logger: self.logger.info("无法打开 https://e-hentai.org/home.php, 请检查网络", str(e))
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
            
    # 解析来自 E-Hentai API 的画廊信息
    def parse_gmetadata(self, data):
        comicinfo = {}
        if 'token' in data:
            comicinfo['Web'] = 'https://exhentai.org/g/{gid}/{token}/'.format(gid=data['gid'],token=data['token'])
        if 'tags' in data:
            comicinfo.update(get_original_tag(data['tags']))
        # 把 Manga 以外的 category 添加到 Tags
        if not data['category'] == 'Manga':
            if 'Tags' in comicinfo:
                comicinfo['Tags'] = comicinfo['Tags'] + ', ' + data['category'].lower()
            else:
                comicinfo['Tags'] = data['category'].lower()
        # 从标题中提取作者信息
        if not data['title_jpn'] == "": text = data['title_jpn']
        else: text = data['title']
        comicinfo['Title'], comicinfo['Writer'], comicinfo['Penciller'] = parse_filename(text)
        # 推测一些 Series 信息
        # 目指せ!楽園計画RX vol.2 (ToLOVEる -とらぶる-)
        r_pattern = [
            r'(.+)\s*vol(.+|.*)\d',
            r'(.+)\W\d'
        ]
        for pattern in r_pattern:
            search_series = re.search(pattern, comicinfo['Title'])
            if not search_series == None:
                comicinfo['Series'] = search_series.group(1).strip()
                break
        return comicinfo
    def _download(self, url, dir):
        try:
            with self.session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(dir, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
            if self.logger:
                self.logger.info(f"下载完成: {dir}")
            return dir
        except Exception as e:
            if self.logger:
                self.logger.error(f"下载失败: {e}")
            return None
    def archive_download(self, url, mode):
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
                            torrent_path = os.path.join(check_dirs('torrents'), max_seeds_torrent['name'])
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
                    if self.logger: self.logger.info("Archive Download Link:", download_url)
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
                    final_url = hrefs[0] + '?start=1'
                    if self.logger: self.logger.info("开始下载: ", final_url)
                    # 返回种子地址
                    return 'archive', final_url
                except Exception as e:
                    # 如果发生了特定类型的异常，执行这里的代码
                    if self.logger: self.logger.info(f"An error occurred: {e}")
