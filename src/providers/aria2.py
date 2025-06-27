import json
import requests
import base64
import time
import sys

class Aria2RPC:
    def __init__(self, url, token, logger=None):
        self.url = url
        self.token = token
        self.headers = {'Content-Type':'application/json'}
        self.id = 0

    def _request(self, method, params=None):
        self.id += 1
        payload = {'jsonrpc':'2.0', 'id':self.id, 'method':method, 'params':[f'token:{self.token}']}
        if params: payload['params'].extend(params)
        #print(params)
        response = requests.post(self.url, headers=self.headers, data = json.dumps(payload), timeout=10)
        return response.json()

    def add_uri(self, uri, dir=None, out=None):
        data = {}
        if dir != None: data['dir'] = dir
        if out != None: data['out'] = out
        return self._request('aria2.addUri', [[uri], data])

    def add_torrent(self, torrent, dir=None, out=None):
        # 读取 .torrent 文件并进行 base64 编码
        with open(torrent, 'rb') as torrent_file:
            torrent_data = torrent_file.read()
            torrent_base64 = base64.b64encode(torrent_data).decode('utf-8')
        data = {}
        if dir != None: data['dir'] = dir
        if out != None: data['out'] = out
        return self._request('aria2.addTorrent', [torrent_base64, [], data])

    def tell_active(self):
        return self._request('aria2.tellActive')

    def tell_waiting(self):
        return self._request('aria2.tellWaiting', [0,1000] )

    def tell_status(self, gid):
        return self._request('aria2.tellStatus', [gid])

    def pause(self, gid):
        return self._request('aria2.pause', [gid])

    def unpause(self, gid):
        return self._request('aria2.unpause', [gid])

    def remove(self, gid):
        return self._request('aria2.remove', [gid])

    def get_global_stat(self):
        return self._request('aria2.getGlobalStat')

    def get_version(self):
        return self._request('aria2.getVersion')

    def listen_status(self, gid, logger=None):
        result = self.tell_status(gid)
        totallen = int(result['result']['totalLength'])
        
        elapsed_time = 0
        elapsed_time_2 = 0

        while True:
            result = self.tell_status(gid)
            status = result['result']['status']
            completelen = int(result['result']['completedLength'])
            download_speed = int(result['result']['downloadSpeed'])

            # 写入日志
            if logger:
                logger.info(f"Status: {status}, Downloaded: {completelen}/{totallen} B, Speed: {download_speed} B/s")

            if completelen == 0:
                elapsed_time += 5
                if elapsed_time >= 300:
                    if logger:
                        logger.warning("No progress for 5 minutes, removing task.")
                    self.remove(gid)
                    return None

            if download_speed == 0:
                elapsed_time_2 += 5
                if elapsed_time_2 >= 7200:
                    if logger:
                        logger.warning("No speed for 2 hours, removing task.")
                    self.remove(gid)
                    return None

            if status == 'complete':
                if logger:
                    logger.info("Download complete.")
                time.sleep(5)
                return result['result']['files'][0]['path']
            else:
                time.sleep(5)

            if status == 'removed':
                if logger:
                    logger.info("Download cancelled.")
                return None