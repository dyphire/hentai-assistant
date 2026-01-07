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

    def _request(self, method, params=None, max_retries=3):
        """发送 JSON-RPC 请求,带重试机制"""
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                self.id += 1
                payload = {
                    'jsonrpc': '2.0',
                    'id': self.id,
                    'method': method,
                    'params': [f'token:{self.token}']
                }
                if params:
                    payload['params'].extend(params)
                
                response = requests.post(
                    self.url,
                    headers=self.headers,
                    data=json.dumps(payload),
                    timeout=60
                )
                response.raise_for_status()
                return response.json()
                
            except (requests.Timeout, requests.ConnectionError) as e:
                last_exception = e
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避: 1s, 2s, 4s
                    time.sleep(wait_time)
                    continue
                raise
            except requests.HTTPError as e:
                last_exception = e
                if e.response.status_code >= 500 and attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    time.sleep(wait_time)
                    continue
                raise
            except json.JSONDecodeError as e:
                last_exception = e
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise
        
        # 如果所有重试都失败,抛出最后一个异常
        if last_exception:
            raise last_exception

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

    def listen_status(self, gid, logger=None, task_id=None, tasks=None, tasks_lock=None):
        """监听 aria2 下载状态,只依赖 aria2 的明确失败信号"""
        last_logged_progress = -1  # 上次记录的进度
        last_log_time = 0  # 上次记录日志的时间
        first_error_time = None  # 首次 API 错误时间
        max_error_duration = 3600  # 最大容忍 API 错误时长(秒),默认1小时
        elapsed_time = 0  # 无进度累计时间(用于判断死种)
        elapsed_time_2 = 0  # 无速度累计时间(用于判断死种)

        while True:
            # 检查任务是否被用户取消
            if task_id and tasks and tasks_lock:
                with tasks_lock:
                    task = tasks.get(task_id)
                    if task and task.cancelled:
                        if logger:
                            logger.info(f"任务 {task_id} 被用户取消，正在停止 aria2 下载")
                        try:
                            self.remove(gid)
                        except Exception as e:
                            if logger:
                                logger.warning(f"停止 aria2 下载失败: {e}")
                        return None

            try:
                result = self.tell_status(gid)
                first_error_time = None  # API 请求成功,重置错误时间
                status = result['result']['status']
                
                # 如果下载文件已经存在, 且未在 Aria2 开启 --allow-overwrite, 则会报错并返回 errorCode 13, 此时直接返回文件路径
                if status == 'error' and result['result'].get('errorCode') == "13":
                    if logger:
                        logger.info("文件已存在，下载任务将被跳过")
                    return result['result']['files'][0]['path']
                
                completelen = int(result['result']['completedLength'])
                totallen = int(result['result']['totalLength'])
                download_speed = int(result['result']['downloadSpeed'])

                # 计算进度百分比
                progress = 0
                if totallen > 0:
                    progress = min(100, int((completelen / totallen) * 100))

                # 更新任务进度信息
                if task_id and tasks and tasks_lock:
                    with tasks_lock:
                        if task_id in tasks:
                            tasks[task_id].progress = progress
                            tasks[task_id].downloaded = completelen
                            tasks[task_id].total_size = totallen
                            tasks[task_id].speed = download_speed

                # 智能日志策略：根据进度调整日志频率
                current_time = time.time()
                
                # 早期频繁打印（前10%）
                if progress < 10:
                    log_interval = 10  # 10秒
                    progress_threshold = 2  # 2%
                # 中期适中（10%-90%）
                elif progress < 90:
                    log_interval = 30  # 30秒
                    progress_threshold = 5  # 5%
                # 后期频繁（90%+）
                else:
                    log_interval = 10  # 10秒
                    progress_threshold = 2  # 2%
                
                should_log = (
                    abs(progress - last_logged_progress) >= progress_threshold or
                    current_time - last_log_time >= log_interval or
                    status in ['complete', 'error', 'removed']
                )
                
                if should_log and logger:
                    # 格式化速度显示
                    if download_speed >= 1024 * 1024:
                        speed_str = f"{download_speed / (1024 * 1024):.2f} MB/s"
                    elif download_speed >= 1024:
                        speed_str = f"{download_speed / 1024:.2f} KB/s"
                    else:
                        speed_str = f"{download_speed} B/s"
                    
                    logger.info(
                        f"Aria2 [{status}] {progress}% "
                        f"({self._format_size(completelen)}/{self._format_size(totallen)}) "
                        f"@ {speed_str}"
                    )
                    last_logged_progress = progress
                    last_log_time = current_time

                # 文件已完成长度达到总长度
                if completelen >= totallen and totallen > 0:
                    if logger:
                        logger.info("文件已下载完成，等待最多 5 秒确认 status 完成")
                    wait_sec = 0
                    while status != 'complete' and wait_sec < 5:
                        time.sleep(1)
                        wait_sec += 1
                        result = self.tell_status(gid)
                        status = result['result']['status']
                    if status != 'complete' and logger:
                        logger.info("status 仍未更新为 complete，但已视为完成")
                    return result['result']['files'][0]['path']

                # 任务完成
                if status == 'complete':
                    if logger:
                        logger.info("Download complete.")
                    time.sleep(5)
                    return result['result']['files'][0]['path']

                # 任务失败或被移除
                if status in ['removed', 'error']:
                    if logger:
                        error_msg = result['result'].get('errorMessage', 'Unknown error')
                        logger.error(f"Aria2 任务失败: status={status}, error={error_msg}")
                    return None

                # 判断死种: 5分钟无进度
                if completelen == 0:
                    elapsed_time += 5
                    if elapsed_time >= 300:
                        if logger:
                            logger.warning("No progress for 5 minutes, removing task.")
                        self.remove(gid)
                        return None
                else:
                    elapsed_time = 0  # 有进度则重置计时器

                # 判断死种: 2小时无速度
                if download_speed == 0:
                    elapsed_time_2 += 5
                    if elapsed_time_2 >= 7200:
                        if logger:
                            logger.warning("No speed for 2 hours, removing task.")
                        self.remove(gid)
                        return None
                else:
                    elapsed_time_2 = 0  # 有速度则重置计时器

                # 其他状态(active, waiting, paused)继续监听
                time.sleep(5)
                
            except Exception as e:
                # API 请求失败,记录警告但不立即判定任务失败
                current_time = time.time()
                
                # 记录首次错误时间
                if first_error_time is None:
                    first_error_time = current_time
                
                # 计算持续错误时长
                error_duration = current_time - first_error_time
                
                if logger:
                    logger.warning(
                        f"获取 aria2 状态时发生异常，将继续重试 "
                        f"(已持续 {int(error_duration)}秒): {e}"
                    )
                
                # 超过最大容忍时长,判定为 aria2 服务不可用
                if error_duration > max_error_duration:
                    if logger:
                        logger.error(
                            f"连续 {int(error_duration)}秒 无法连接 aria2 服务，"
                            f"判定为服务不可用，任务失败"
                        )
                    return None
                
                time.sleep(5)
                continue

    def _format_size(self, bytes_value):
        """格式化文件大小显示"""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_value < 1024:
                return f"{bytes_value:.1f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.1f} TB"
