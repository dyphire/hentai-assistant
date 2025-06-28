import requests
from urllib.parse import urlparse

from utils import is_url

class KomgaAPI:
    def __init__(self, server, token, logger=None):
        self.server = server
        self.headers = {'X-API-Key': token, 'accept': '*/*', 'Content-Type': 'application/json'}
        session = requests.Session()
        session.headers.update(self.headers)
        self.session = session
        if logger: self.logger = logger

    def _valid_session(self):
        try:
            response = self.session.get(self.server + '/api/v1/login/set-cookie', timeout=10)
            if response.status_code == 204:
                return True
            else:
                if self.logger: self.logger.error(f"Session validation failed with status code: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            if self.logger: self.logger.error(f"Error validating session: {e}")
            return False
    def get_libraries(self, library_id=None):
        if not library_id == None:
            return self.session.get(f'{self.server}/api/v1/libraries/{library_id}')
        else:
            return self.session.get(self.server + '/api/v1/libraries')
        
    def scan_library(self, library_id, deep=False):
        if deep == False:
            return self.session.post(self.server + f'/api/v1/libraries/{library_id}/scan?deep=false')
        elif deep == True:
            return self.session.post(self.server + f'/api/v1/libraries/{library_id}/scan?deep=true')
    def get_book(self, text):
        # 获取特定 bookId 的信息
        if is_url(text):
            parsed_url = urlparse(text)
            last_segment = parsed_url.path.strip('/').split('/')[-1]
            if 'book' in text:
                book_id = last_segment
            if 'oneshot' in text:
                # 单行本通过 api/v1/books/list
                series_id = last_segment
                request_body = {
                    "condition": {
                        "allOf": [
                            {
                                "oneShot": { "operator": "isTrue" }
                            },
                            {
                                "seriesId": {
                                "operator": "is",
                                "value": f"{series_id}"
                            }
                            }
                        ]
                    }
                }
                return self.session.post(self.server + f'/api/v1/books/list', data=request_body)['content'][0]
        else:
            book_id = text
        return self.session.get(self.server + f'/api/v1/books/{book_id}')

    def get_series(self, text):
        if is_url(text):
            parsed_url = urlparse(text)
            last_segment = parsed_url.path.strip('/').split('/')[-1]
            if 'oneshot' or 'series' in text: series_id = last_segment
        else:
            series_id = text
        return self.session.get(self.server + f'/api/v1/series/{series_id}')

    def get_collections(self, id=None, library_id=None):
        # 未提供具体 id 的情况, 获取指定 library 的所有合集
        if id == None and not library_id == None:
            url_params = f'?library_id={library_id}?size=99999'
        elif not id == None:
            url_params = ''
        return self.session.get(self.server + f'/api/v1/collections{url_params}')
    def updata_metadata_old(self, metadata, book_data, logger=None):
        # book_id 和 book_data 均可, book_id 的情况多做一次 get_book
        if type(book_data) != "dict":
            book_data = self.get_book(book_data)
        # metadata 中也包含一些 series level 的数据,因此也要同时获取 series_data 用于合并数据
        series_id = book_data['seriesId']
        series_data = self.get_series(series_id)
        if logger:  logger.info('开始写入数据', metadata)
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
                tags.append(t.lower())
            # 对 tag 去重
            book_params['tags'] = tags
            for i in book_data['metadata']['tags']:
                if i not in tags:
                    book_params['tags'].append(i)
        # 提交 book level 的数据
        self.session.patch(self.server + f'/api/v1/books/{book_data['id']}/metadata', json=book_params)
        
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
                tags.append(t.lower())
            series_params['tags'] = list(set(t.lower() for t in series_data['metadata']['tags'] + tags))
        if series_data['metadata']['ageRatingLock'] == False:
            if 'AgeRating' in metadata:
                if '18' in metadata['AgeRating']:
                    series_params['agerating'] = 18
                    series_params['ageRatingLock'] = True
        if 'Manga' in metadata and metadata['Manga'] == "YesAndRightToLeft":
            series_params['readingDirection'] = "RIGHT_TO_LEFT"
        self.session.patch(self.server + f'/api/v1/series/{series_data['id']}/metadata', json=series_params)

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
                    if 'collection' in c['name']: # 已经存在合集的情况
                        collections_params['seriesIds'] = collections_params['seriesIds'] + c['seriesIds']
                        self.session.patch(self.server + f'/api/v1/collections/{c['id']}', params=collections_params)
                        break
                    else: # 否则,新建一个合集
                        self.session.patch(self.server + f'/api/v1/collections/', params=collections_params)