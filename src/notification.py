import requests
import datetime
import apprise
from utils import TaskStatus
from providers.komga import EventListener, KomgaAPI
import logging
from config import load_config


def notify(event, data, logger=None, app_config=None):
    if not app_config:
        return
    
    notification_config = app_config.get('notification', {})
    notify_events = app_config.get('notify_events', {})

    if event not in notify_events:
        return

    # 获取为该事件配置的通知服务
    services_to_notify = notify_events[event]

    # 处理 Webhook 通知
    webhook_keys = [s for s in services_to_notify if 'webhook' in s]
    if webhook_keys:
        webhook_urls = [notification_config.get(key) for key in webhook_keys if notification_config.get(key)]
        if webhook_urls:
            # 将所有 URL 合并为一个逗号分隔的字符串
            all_urls = ",".join(webhook_urls)
            send_webhook(url=all_urls, event=event, data=data, logger=logger)

    # 处理 Apprise 通知
    apprise_keys = [s for s in services_to_notify if 'apprise' in s]
    if apprise_keys:
        apprise_urls = [notification_config.get(key) for key in apprise_keys if notification_config.get(key)]
        send_apprise(apprise_urls=apprise_urls, event=event, data=data, logger=logger)
        

def send_apprise(apprise_urls, event, data, logger=None):
    """Handles sending notifications via Apprise."""
    if not apprise_urls:
        return

    apobj = apprise.Apprise()
    for url in apprise_urls:
        apobj.add(url)

    if event == 'komga.new':
        title = "Komga 新书入库"
        message_list = [
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
        message_list = [f"任务ID: {data.get('task_id')}", f"URL: {data.get('url')}"]
        if event in ['task.error', 'task.cancel']:
            message_list.append(f"失败原因: {data.get('error', '未知错误')}")
        if event == 'task.complete':
            # task.complete 会包含来自 parse_metadata() 返回的 metadata 信息
            details = {
                'Title': '标题',
                'Writer': '作者',
                'Penciller': '画师',
                'AlternateSeries': '系列',
            }
            complete_message_list = []
            metadata = data.get('metadata', {})
            for key, label in details.items():
                value = metadata.get(key)
                if value:
                    complete_message_list.append(f"{label}: {value}")
            
            tags = metadata.get('Tags')
            if tags:
                complete_message_list.append(f"标签: {tags}")
            message_list.extend(complete_message_list)
    
    message_body = "\n".join(message_list)
    
    if apobj.notify(body=message_body, title=title):
        if logger: logger.info(f"Sent notification for event '{event}' via Apprise to {len(apprise_urls)} destination(s)")
    else:
        if logger: logger.error(f"Failed to send notification for event '{event}' via Apprise")


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

def listen_event(komga_server: str, komga_username: str, komga_password: str, app_config: dict):
    """监听 Komga SSE 事件并触发通知"""
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
            if event_type == 'ThumbnailBookAdded':
                book_id = event['data'].get('bookId')
                if book_id and book_id == last_processed_book_id:
                    listener_logger.warning(f"从 SSE Events 连续收到重复的事件: {book_id}, 跳过处理")
                    continue
                
                last_processed_book_id = book_id
                
                book_data = KomgaAPI(komga_server, komga_username, komga_password, logger=listener_logger).get_book(book_id).json()
                
                # 调用统一的 notify 函数，而不是直接调用 send_webhook
                notify(event="komga.new", data=book_data, logger=listener_logger, app_config=app_config)

if __name__ == "__main__":
    # 加载配置
    config_data = load_config()
    komga_config = config_data.get('komga', {})
    notification_config = config_data.get('notification', {})

    # 检查 Komga 和通知功能是否启用
    if not komga_config.get('enable') or not notification_config.get('enable'):
        logging.getLogger("komga_listener").info("Komga 或通知功能未启用，监听器将不会启动。")
    else:
        komga_server = komga_config.get('server')
        komga_username = komga_config.get('username')
        komga_password = komga_config.get('password')

        # 构建 notify 函数需要的 app_config 结构
        notify_events = {}
        for e_key in ['task.start', 'task.complete', 'task.error',  'komga.new']:
            config_value = notification_config.get(e_key, '').strip()
            if config_value:
                notify_events[e_key] = [item.strip() for item in config_value.split(',') if item.strip()]

        app_config_for_listener = {
            'notification': notification_config,
            'notify_events': notify_events
        }

        # 确保所有必要信息都已配置
        if all([komga_server, komga_username, komga_password]) and 'komga.new' in notify_events:
            listen_event(komga_server, komga_username, komga_password, app_config_for_listener)
        else:
            logger = logging.getLogger("komga_listener")
            if 'komga.new' not in notify_events:
                logger.info("配置文件中未针对 'komga.new' 事件进行设置，监听器将不会启动。")
            else:
                logger.warning("Komga 服务器、用户名或密码未配置完整，监听器无法启动。")