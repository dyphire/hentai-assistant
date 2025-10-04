import requests
import datetime
import apprise
from utils import TaskStatus
from providers.komga import EventListener, KomgaAPI
import logging

class AppriseConfig:
    def __init__(self, url):
        self.url = url

    def send_message(self, message, title):
        apobj = apprise.Apprise()
        # 添加通知服务 URL（这里是 Telegram 示例）
        apobj.add(self.url)
        # 发送通知
        apobj.notify(
            body=message,  # 消息体
            title=title   # 可选：标题
        )

def notify(event, data, logger=None, app_config=None):
    if app_config:
        # webhook 只需要在 json 中附带数据
        webhook_url = app_config.get('notify_webhook')
        if webhook_url and 'webhook' in app_config['notify_events'][event]:
            send_webhook(url=webhook_url, event=event, data=data)
        # apprise 使用特定模板
        apprise_url = app_config.get('notify_apprise')
        if apprise_url and 'apprise' in app_config['notify_events'][event]:
            msg = AppriseConfig(apprise_url)
            if event == 'komga.new':
                title = "Komga 新书入库"
                message = [
                    f"书名: {data.get('name')}",
                    f"作者: {', '.join(data.get('metadata', {}).get('authors', []))}",
                    f"系列: {data.get('metadata', {}).get('series', 'N/A')}",
                    f"标签: {', '.join(data.get('metadata', {}).get('tags', []))}",
                    f"语言: {data.get('metadata', {}).get('language', 'N/A')}",
                    f"页数: {data.get('metadata', {}).get('pages', 'N/A')}",
                    f"添加时间: {data.get('addedAt', 'N/A')}",
                    f"链接: {data.get('url', 'N/A')}"
                ]
            else:
                title = f"Hentai Assistant 任务通知 - {event}"
                message = [f"任务ID: {data.get('task_id')}"]
                if event in ['task.error', 'task.cancel']:
                    message.append(f"失败原因: {data.get('error', 'N/A')}")
                if event == 'task.complete':
                    message.append(f"文件路径: {data.get('file_path', 'N/A')}")
            msg.send_message(message=("\n").join(message), title=title)
            if logger: logger.info(f"Sent notification for event '{event}' via Apprise")
        

def send_webhook(url, event, data, logger=None):
    payload = {
            "event": event,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": data
            }
    try:
        url_list = [item.strip() for item in url.split(",")]
        for u in url_list:
            if logger: logger.info(f"Sending webhook notification for event '{event}' to {u}")
            response = requests.post(u, json=payload)
            response.raise_for_status()
            print(f"Webhook sent successfully to {u}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to send webhook to {u}: {e}")

def listen_event(komga_server: str, komga_username: str, komga_password: str, webhook_url):
    
    sse_url = f"{komga_server}/sse/v1/events"
    listener_logger = logging.getLogger("komga_listener")
    listener_logger.setLevel(logging.INFO)
    if not listener_logger.handlers:
        console_handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] [KomgaListener] %(message)s')
        console_handler.setFormatter(formatter)
        listener_logger.addHandler(console_handler)
    client = EventListener(url=sse_url, username=komga_username, password=komga_password, logger=listener_logger)
    listener_logger.info(f"开始监听SSE事件流: {sse_url}")

    last_processed_book_id = None

    for event in client.listen():
        event_type = event.get('event_type')
        if event_type and event_type != 'TaskQueueStatus':
            listener_logger.info(f"从监听器收到事件: {event}")
            # 为新入库事件关联元数据，考虑到 BookAdded 事件可能在元数据写入前触发，改为监听 ThumbnailBookAdded 事件
            if event_type == 'ThumbnailBookAdded':
                book_id = event['data'].get('bookId')
                if book_id and book_id == last_processed_book_id:
                    listener_logger.warning(f"从 SSE Events 连续收到重复的事件: {book_id}, 跳过处理")
                    continue
                
                last_processed_book_id = book_id
                
                book_data = KomgaAPI(komga_server, komga_username, komga_password, logger=listener_logger).get_book(book_id).json()
                listener_logger.info(f'sending webhook for new book to {webhook_url}')
                send_webhook(url=webhook_url, event="komga.new", data=book_data, logger=listener_logger)

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Komga Notification Listener")
    parser.add_argument('--komga_server', type=str, required=True, help="Komga server URL")
    parser.add_argument('--komga_username', type=str, required=True, help="Komga username")
    parser.add_argument('--komga_password', type=str, required=True, help="Komga password")
    parser.add_argument('--webhook_url', type=str, required=True, help="Webhook URL")
    
    
    args = parser.parse_args()
    listen_event(args.komga_server, args.komga_username, args.komga_password, args.webhook_url)