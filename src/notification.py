import requests
import datetime
import apprise
from utils import TaskStatus
from providers.komga import EventListener, KomgaAPI
import logging
from config import load_config


def notify(event, data, logger=None, notification_config=None):
    if not notification_config:
        # 如果未提供配置，尝试从 config.py 加载
        notification_config = load_config().get('notification', {})

    if not notification_config or not notification_config.get('enable'):
        return

    apprise_notifiers = []
    webhook_notifiers = []

    # notifiers 现在是一个字典，其中键是 notifier 的名称
    for notifier_name, notifier_details in notification_config.items():
        # 跳过 'enable' 键
        if notifier_name == 'enable':
            continue

        if notifier_details.get('enable') and event in notifier_details.get('events', []):
            notifier_type = notifier_details.get('type', '').lower()
            url = notifier_details.get('url')
            if not url:
                continue
            
            # 将 notifier_details 作为一个整体传递，而不是原来的 notifier 变量
            if notifier_type == 'apprise':
                apprise_notifiers.append(notifier_details)
            elif notifier_type == 'webhook':
                webhook_notifiers.append(notifier_details)

    if webhook_notifiers:
        send_webhook(notifiers=webhook_notifiers, event=event, data=data, logger=logger)
    
    if apprise_notifiers:
        send_apprise(notifiers=apprise_notifiers, event=event, data=data, logger=logger)
        

def send_apprise(notifiers, event, data, logger=None):
    """Handles sending notifications via Apprise."""
    if not notifiers:
        return

    apobj = apprise.Apprise()
    for notifier in notifiers:
        apobj.add(notifier.get('url'))

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
        destinations = ", ".join([f"{n.get('name', 'Untitled')}({n.get('url')})" for n in notifiers])
        if logger: logger.info(f"Sent notification for event '{event}' via Apprise to: {destinations}")
    else:
        if logger: logger.error(f"Failed to send notification for event '{event}' via Apprise")


def send_webhook(notifiers, event, data, logger=None):
    payload = {
            "event": event,
            "timestamp": datetime.datetime.now().isoformat(),
            "data": data
            }
    for notifier in notifiers:
        name = notifier.get('name', 'Untitled')
        url = notifier.get('url')
        try:
            if logger: logger.info(f"Sending webhook notification for event '{event}' to {name}({url})")
            response = requests.post(url, json=payload)
            response.raise_for_status()
            print(f"Webhook sent successfully to {name}({url})")
        except requests.exceptions.RequestException as e:
            print(f"Failed to send webhook to {name}({url}): {e}")

def listen_event(komga_server: str, komga_username: str, komga_password: str, notification_config: dict):
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
                notify(event="komga.new", data=book_data, logger=listener_logger, notification_config=notification_config)

if __name__ == "__main__":
    # 加载配置
    config_data = load_config()
    komga_config = config_data.get('komga', {})
    notification_config = config_data.get('notification', {})
    logger = logging.getLogger("komga_listener")

    # 检查 Komga 和通知功能是否启用
    if not komga_config.get('enable'):
        logger.info("Komga 功能未启用，监听器将不会启动。")
    else:
        komga_server = komga_config.get('server')
        komga_username = komga_config.get('username')
        komga_password = komga_config.get('password')

        # 检查是否有任何通知器订阅了 'komga.new' 事件
        # 检查是否有任何已启用的通知器订阅了 'komga.new' 事件
        komga_new_event_configured = any(
            details.get('enable') and 'komga.new' in details.get('events', [])
            for name, details in notification_config.items() if name != 'enable'
        )

        # 确保所有必要信息都已配置
        if all([komga_server, komga_username, komga_password]) and komga_new_event_configured:
            listen_event(komga_server, komga_username, komga_password, notification_config)
        else:
            if not komga_new_event_configured:
                logger.info("配置文件中未针对 'komga.new' 事件进行设置，监听器将不会启动。")
            else:
                logger.warning("Komga 服务器、用户名或密码未配置完整，监听器无法启动。")