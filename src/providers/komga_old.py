import requests
import traceback
import json
import os, re, time
import zipfile
from providers import ehentai
from utils import *
from urllib.parse import urlparse

class KomgaAPI:
    def __init__(self, server, token):
        self.url = server
        self.headers = {'X-API-Key': token, 'Accept': 'application/json'}
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
    def _request(self, method, controller, params=None):
        if method.lower() == 'get':
            response = requests.get(self.url + controller, auth=self.auth)
            if response.status_code == 200:
                print(f"{method.upper()} {controller} 成功")
                if 'content' in response.json():
                            return response.json()['content']
                else:
                    return response.json()
            else: print(f"Request failed with status code: {response.status_code}")
        if method.lower() == 'post':
            response = requests.post(self.url + controller, headers={'accept': '*/*', 'Content-Type': 'application/json'}, data=json.dumps(params), auth=self.auth)
        if method.lower() == 'patch':
            response = requests.patch(self.url + controller, headers={'accept': '*/*', 'Content-Type': 'application/json'}, data=json.dumps(params), auth=self.auth)
            return response

    def get_libraries(self, library_id=None):
        if not library_id == None: return self._request(method='get', controller=f'/api/v1/libraries/{library_id}')
        else: return self._request(method='get', controller=f'/api/v1/libraries')

    def scan_library(self, library_id, deep=False):
        if deep == False: return self._request(method='post', controller=f'/api/v1/libraries/{library_id}/scan?deep=false')
        elif deep == True: return self._request(method='post', controller=f'/api/v1/libraries/{library_id}/scan?deep=true')

    def get_all_books(self, series_id=None, library_id=None):
        if not series_id == None:
            return self._request(method='get', controller=f'/api/v1/series/{series_id}/books')
        if not library_id == None:
            return self._request(method='get', controller=f'/api/v1/books?library_id={library_id}&size=99999')

    def get_book(self, text):
        if is_url(text):
            parsed_url = urlparse(text)
            last_segment = parsed_url.path.strip('/').split('/')[-1]
            if 'book' in text:
                book_id = last_segment
            if 'oneshot' in text:
                series_id = last_segment
                return self.get_series_books(series_id)[0]
        else:
            book_id = text
        return self._request(method='get', controller=f'/api/v1/books/{book_id}')

    def get_series(self, text):
        if is_url(text):
            parsed_url = urlparse(text)
            last_segment = parsed_url.path.strip('/').split('/')[-1]
            if 'oneshot' or 'series' in text: series_id = last_segment
        else:
            series_id = text
        return self._request(method='get', controller=f'/api/v1/series/{series_id}')

    def get_collections(self, id=None, library_id=None):
        # 未提供具体 id 的情况, 获取指定 library 的所有合集
        if id == None and not library_id == None:
            url_params = f'?library_id={library_id}?size=99999'
        elif not id == None:
            url_params = ''
        return self._request(method='get',controller=f'/api/v1/collections{url_params}')

    def updata_metadata(self, metadata, book_data):
        # book_id 和 book_data 均可, book_id 的情况多做一次 get_book
        if type(book_data) != "dict":
            book_data = self.get_book(book_data)
        # metadata 中也包含一些 series level 的数据,因此也要同时获取 series_data 用于合并数据
        series_id = book_data['seriesId']
        series_data = self.get_series(series_id)
        print('开始写入数据', metadata)
        series_params = {}
        # 先处理 book level 的数据
        book_params = {}
        if 'Title' in metadata:
            book_params['title'] = metadata['Title']
            book_params['titleSort'] = metadata['Title']
        if 'Web' in metadata:
            print(metadata['Web'])
            if 'anilist' in metadata['Web']: label = 'AniList'
            elif 'mangaupdates' in metadata['Web']: label = 'MangaUpdates'
            elif 'hentai' in metadata['Web']: label = 'E-Hentai'
            elif 'chaika' in metadata['Web']: label = 'Chaika Panda'
            else: label = urlparse(metadata['Web']).hostname
            link = {
                'label' : label,
                'url' : metadata['Web']
                    }
            book_params['links'] = book_data['metadata']['links']
            # 去重
            is_link_existed = False
            for l in book_params['links']:
                if l['label'] == link['label']:
                    l['url'] = link['url']
                    is_link_existed = True
                    break
            if not is_link_existed == True:
                book_params['links'].append(link)
        authors = []
        if 'Writer' in metadata:
            for w in metadata['Writer'].split(', '):
                authors.append({'name' : w, 'role' : 'writer'})
        if 'Penciller' in metadata:
            for p in metadata['Penciller'].split(', '):
                authors.append({'name' : p, 'role' : 'penciller'})
        if len(authors) > 0:
            book_params['authors'] = authors
            book_params['authorsLock'] = True
            print('authors updated')
        if 'Tags' in metadata:
            tags = []
            for t in metadata['Tags'].split(', '):
                tags.append(ehentai.anilist_tags_conv(t.lower()))
            # 对 tag 去重
            book_params['tags'] = tags
            for i in book_data['metadata']['tags']:
                if i not in tags:
                    book_params['tags'].append(i)
        # 提交 book level 的数据
        self._request(method='patch', controller=f'/api/v1/books/{book_data['id']}/metadata', params=book_params)
        
        # 接着处理 series level 的数据
        if 'Series' in metadata:
            series_params['Title'] = metadata['Series']
            series_params['titleSort'] = metadata['Series']
        if 'Count' in metadata:
            if series_data['metadata']['totalBookCountLock'] == False:
                series_params['totalBookCount'] = metadata['Count']
                series_params['totalBookCountLock'] = True
                series_params['status'] = 'ENDED'
                series_params['statusLock'] = True
        if 'Genre' in metadata:
            genres = metadata['Genre'].lower().split(', ')
            mergedgenres = series_data['metadata']['genres'] + genres
            series_params['genres'] = list(set(mergedgenres))
        if 'SeriesTags' in metadata:
            tags = []
            for t in metadata['SeriesTags'].split(', '):
                tags.append(ehentai.anilist_tags_conv(t.lower()))
            series_params['tags'] = list(set(t.lower() for t in series_data['metadata']['tags'] + tags))
        if series_data['metadata']['ageRatingLock'] == False:
            if 'AgeRating' in metadata:
                if '18' in metadata['AgeRating']:
                    series_params['agerating'] = 18
                    series_params['ageRatingLock'] = True
        # 为指定媒体库强制RTL
        if book_data['libraryId'] in ['0BKK1MS5P8DMJ', '0AY8X5XNW431M']:
            series_params['readingDirection'] = "RIGHT_TO_LEFT"
        self._request(method='patch', controller=f'/api/v1/series/{series_data['id']}/metadata', params=series_params)

        # 有 collections 的情况
        if 'SeriesGroup' in metadata:
            for s in metadata['SeriesGroup'].split(', '):
                print(f'将 {s} 添加至收藏集')
                # add_to_collections(series_data['id'], collection=s)
                collections_params = {
                    "name": s,
                    "ordered": False,
                    "seriesIds": [
                        series_id
                    ]
                }
                for c in self.get_collections(library_id=series_data['libraryId']):
                    if collection in c['name']: # 已经存在合集的情况
                        collections_params['seriesIds'] = collections_params['seriesIds'] + c['seriesIds']
                        self._request(method='patch', controller=f'/api/v1/collections/{c['id']}', params=collections_params)
                        break
                    else: # 否则,新建一个合集
                        self._request(method='post', controller=f'/api/v1/collections/', params=collections_params)

def get_books(bookid=None, seriesid=None, libraryid=None, lastest=False):
    if not bookid == None:
        controller = '/api/v1/books/' + bookid
    elif not seriesid == None:
        controller = '/api/v1/series/{seriesid}/books'.format(seriesid=seriesid)
    elif not libraryid == None:
        controller = '/api/v1/books?library_id=' + libraryid
    elif lastest == True:
        controller = '/api/v1/books/latest'
    else:
        controller = '/api/v1/books'
    try:
        result = requests.get(BASIC_URL + controller, auth=AUTH)
        if 'content' in result.json():
            return result.json()['content']
        else:
            return result.json()
    except:
        print("getOnePage Undefined Error")
        print(traceback.format_exc())
        return False
    
def get_series(seriesid=None, libraryid=None, lastest=False):
    if not seriesid == None:
        controller = BASIC_URL + '/api/v1/series/' + seriesid
    elif not libraryid == None:
        controller = BASIC_URL + '/api/v1/series?library_id=' + libraryid
    elif lastest == True:
        controller = BASIC_URL + '/api/v1/series/latest'
    else:
        controller = BASIC_URL + '/api/v1/series'
    try:
        result = requests.get(controller, auth=AUTH)
        if 'content' in result.json():
            return result.json()['content']
        else:
            return result.json()
    except:
        print("getOnePage Undefined Error")
        print(traceback.format_exc())
        return False

def get_oneshot(seriesid):
    controller =  BASIC_URL + '/api/v1/series/' + seriesid + '/books'
    try:
        result = requests.get(controller, auth=AUTH)
        if result.status_code == 200:
            return result.json()['content'][0]
    except:
        print("getOnePage Undefined Error")
        print(traceback.format_exc())
        return False
    
def get_collections(libraryid=None):
    if not libraryid == None:
        params = '?library_id=0BKK1MS5P8DMJ'
    else:
        params = ''
    try:
        result = requests.get(BASIC_URL + '/api/v1/collections' + params + '?size=999', auth=AUTH)            
        return result.json()['content']
    except:
        print("searchSeries Undefined Error")
        print(traceback.format_exc())
        return False
    
def get_libraries(libraryid=None, libraryname=None):
    if not libraryid == None:
        controller = BASIC_URL + '/api/v1/libraries/' + libraryid
    else:
        controller = BASIC_URL + '/api/v1/libraries'
    try:
        result = requests.get(controller, auth=AUTH)
        return result.json()
    except:
        print("getOnePage Undefined Error")
        print(traceback.format_exc())
        return False

def list_providers(library):
    for c in config.providers:
        if c == library.lower():
            return [f.strip(' ') for f in config.providers[c].split(',')]
    return [f.strip(' ') for f in config.providers['Default'].split(',')]

def patch_metadata(id, params, level="Books"):
    controller = BASIC_URL + '/api/v1/{level}/{id}/metadata'.format(level=level, id=id)
    try:
        print('正在应用数据:',params)
        result = requests.patch(controller, headers={'accept': '*/*', 'Content-Type': 'application/json'}, data=json.dumps(params), auth=AUTH)
    except:
        print("patchSerieMetadata Undefined Error")
        print(traceback.format_exc())
        return False

def add_to_collections(seriesid, collection):
    collections_params = {
        "name": collection,
        "ordered": False,
        "seriesIds": [
            seriesid
        ]
    }
    controller = BASIC_URL + '/api/v1/collections/'
    for c in get_collections():
        if collection in c['name']:
            collections_params['seriesIds'] = collections_params['seriesIds'] + c['seriesIds']
            try:
                requests.patch(controller + c['id'], data=json.dumps(collections_params), auth=AUTH)
            except:
                print("patchSerieMetadata Undefined Error")
                print(traceback.format_exc())
                return False
        else:
            try:
                requests.post(controller, data=json.dumps(collections_params), auth=AUTH)
            except:
                print("patchSerieMetadata Undefined Error")
                print(traceback.format_exc())
                return False
            
def read_galleryinfo(file_path):
    with zipfile.ZipFile(file_path) as z:
        filelist = z.namelist()
        for f in filelist:
            if 'galleryinfo.txt' in f:
                print('开始解析', f)
                with z.open(f) as gallery_info:
                    text = [t.decode('utf-8') for t in gallery_info.readlines()]
                return text
        

"""def updata_metadata(metadata, book_id):
    book_data = get_books(book_id)
    series_data = get_series(book_data['seriesId'])
    print('开始写入数据', metadata)
    series_params = {}
    book_params = {}
    if 'Web' in metadata:
        print(metadata['Web'])
        if 'anilist' in metadata['Web']: label = 'AniList'
        elif 'mangaupdates' in metadata['Web']: label = 'MangaUpdates'
        elif 'hentai' in metadata['Web']: label = 'E-Hentai'
        elif 'chaika' in metadata['Web']: label = 'Chaika Panda'
        else: label = 'Unknown'
        link = {
            'label' : label,
            'url' : metadata['Web']
                }
        book_params['links'] = book_data['metadata']['links']
        # 去重
        is_link_existed = False
        for l in book_params['links']:
            if l['label'] == link['label']:
                l['url'] = link['url']
                is_link_existed = True
                break
        if not is_link_existed == True:
            book_params['links'].append(link)
    '''            
    if book_data['number'] == 1 and book_data['metadata']['releaseDateLock'] == False:
        if 'releaseDate' in metadata:
            book_params['releaseDate'] = str(metadata['Year']) + '-' + str(metadata['Month']) + '-' + str(metadata['Day'])
            book_params['releaseDateLock'] = True
    '''
    # 获取一份既存的作者列表
    if book_data['metadata']['authorsLock'] == False:
        if 'Writer' in metadata or 'Penciller' in metadata:
            authors = []
            if 'Writer' in metadata:
                for w in metadata['Writer'].split(', '):
                    authors.append({'name' : w, 'role' : 'writer'})
            if 'Penciller' in metadata:
                for p in metadata['Penciller'].split(', '):
                    authors.append({'name' : p, 'role' : 'penciller'})
            book_params['authors'] = authors
            book_params['authorsLock'] = True
            print('authors updated')
    if 'Tags' in metadata:
        tags = []
        for t in metadata['Tags'].split(', '):
            tags.append(ehentai.anilist_tags_conv(t.lower()))
        book_params['tags'] = list(set(t.lower() for t in book_data['metadata']['tags'] + tags))
    patch_metadata(book_data['id'], params=book_params, level='books')
    
    # Series level 
    if 'Title' in metadata:
        series_params['title'] = metadata['Title']
        series_params['titleSort'] = metadata['Title']
    if 'Count' in metadata:
        if series_data['metadata']['totalBookCountLock'] == False:
            series_params['totalBookCount'] = metadata['Count']
            series_params['totalBookCountLock'] = True
            series_params['status'] = 'ENDED'
            series_params['statusLock'] = True
    if 'Genre' in metadata:
        genres = metadata['Genre'].lower().split(', ')
        mergedgenres = series_data['metadata']['genres'] + genres
        series_params['genres'] = list(set(mergedgenres))
    if 'SeriesTags' in metadata:
        tags = []
        for t in metadata['SeriesTags'].split(', '):
            tags.append(ehentai.anilist_tags_conv(t.lower()))
        series_params['tags'] = list(set(t.lower() for t in series_data['metadata']['tags'] + tags))
    if series_data['metadata']['ageRatingLock'] == False:
        if 'AgeRating' in metadata:
            if '18' in metadata['AgeRating']:
                series_params['agerating'] = 18
                series_params['ageRatingLock'] = True
    # 为指定媒体库强制RTL
    if book_data['libraryId'] in ['0BKK1MS5P8DMJ', '0AY8X5XNW431M']:
        series_params['readingDirection'] = "RIGHT_TO_LEFT"
    patch_metadata(series_data['id'], series_params, 'series')
    # Collections level
    if 'SeriesGroup' in metadata:
        for s in metadata['SeriesGroup']:
            add_to_collections(series_data['id'], collection=s)"""

def clean_filename(filename):
    # 去除所有括号内的内容，包括中括号 []、圆括号 ()、大括号 {} 等
    cleaned_filename = re.sub(r'[\[\(【].*?[\]\)】]', '', filename)
    # 去掉文件扩展名，比如 .zip
    cleaned_filename = re.sub(r'\.\w+$', '', cleaned_filename) 
    # 去除前后多余的空格
    cleaned_filename = cleaned_filename.strip()
    return cleaned_filename

def match_book(provider, book_id, series_id):
    # 首先，解析通过bookid获取的文件名
    book_data = get_books(book_id)
    url = book_data['url']
    filename = os.path.basename(url)
    # 得到一个初步的数据
    # 作者已在入库的时候手动设置，无须再次判断
    penciller = os.path.basename(os.path.dirname(os.path.dirname(url)))
    parsed_title = clean_filename(filename)
    # 调用刮削器
    if provider.lower() == 'e-hentai':
        matchEHentai = re.match(r'.*?\[(?P<author>.+?)\]\s*(?P<title>.+?)\s*\[.*?(?P<galleryid>\d+?)\]', book_data['name'])
        # 对来源为EH的项目刮削信息
        if matchEHentai:
            searchwords = matchEHentai.group('galleryid')
        else:
            # 尝试根据文件名搜索
            searchwords = input('没有找到GID，请手动输入画廊的url')
    #metadata = agent.searchMetadata(searchwords, provider=provider)
    if metadata == None:
        if provider == 'E-Hentai':
            print('未找到对应画廊，尝试从 galleryinfo.txt 提取信息')
            if config.pathmapping == None:
                book_path = book_data['url']
            else:
                start = re.search(r'(^\/.+?)\/',book_data['url']).group(1)
                book_path = os.path.join(config.pathmapping, os.path.relpath(book_data['url'],start))
            galleryinfo = read_galleryinfo(book_path)
            metadata = ehentai.parse_galleryinfo(galleryinfo, gid=searchwords)
        elif provider == 'Anilist':
            pass
    updata_metadata(metadata, book_data, series_data)
    
def scan_library(library_name=None):
    libraries = get_libraries()
    for l in libraries:
        provider_list = list_providers(l['name'])
        if not library_name == None:
            if l['name'] == library_name:
                libraryid = l['id']
                print('Search library:',l['id'])
        else:
            libraryid = None
        series_bundle = get_series(libraryid=libraryid)
        for s in series_bundle:
            books_bundle = get_books(seriesid=s['id'])
            for b in books_bundle:
                for p in provider_list:
                    match_book(book_data=b, series_data=s, provider=p)



if __name__ == '__main__':
    auto_penciller('0HBB1XNV9VTWM')