import requests
import datetime
import apprise
from utils import TaskStatus
from providers.komga import EventListener, KomgaAPI
import logging
from config import load_config


def notify(event, data, logger=None, notification_config=None):
    if logger: logger.debug(f"notify 函数被调用, 事件: '{event}'.")

    if not notification_config:
        # 如果未提供配置，尝试从 config.py 加载
        notification_config = load_config().get('notification', {})


    apprise_notifiers = []
    webhook_notifiers = []

    # notifiers 现在是一个字典，其中键是 notifier 的名称
    for notifier_name, notifier_details in notification_config.items():
        # 跳过 'enable' 键
        if notifier_name == 'enable':
            continue

        is_enabled = notifier_details.get('enable', False)
        subscribed_events = notifier_details.get('events', [])
        if logger: logger.debug(f"检查通知器 '{notifier_name}': 启用={is_enabled}, 事件匹配={event in subscribed_events} (已订阅: {subscribed_events})")

        if is_enabled and event in subscribed_events:
            notifier_type = notifier_details.get('type', '').lower()
            url = notifier_details.get('url')
            if not url:
                if logger: logger.warning(f"通知器 '{notifier_name}' 缺少 URL。")
                continue
            
            if logger: logger.debug(f"通知器 '{notifier_name}' 已为事件 '{event}' 配置。正在添加到分发列表。")
            # 将 notifier_details 作为一个整体传递，而不是原来的 notifier 变量
            if notifier_type == 'apprise':
                apprise_notifiers.append(notifier_details)
            elif notifier_type == 'webhook':
                webhook_notifiers.append(notifier_details)

    if webhook_notifiers:
        if logger: logger.debug(f"找到 {len(webhook_notifiers)} 个 webhook 需要通知。")
        send_webhook(notifiers=webhook_notifiers, event=event, data=data, logger=logger)
    else:
        if logger: logger.debug(f"未找到为事件 '{event}' 启用的 webhook。")

    if apprise_notifiers:
        if logger: logger.debug(f"找到 {len(apprise_notifiers)} 个 apprise 通知器需要通知。")
        send_apprise(notifiers=apprise_notifiers, event=event, data=data, logger=logger)
    else:
        if logger: logger.debug(f"未找到为事件 '{event}' 启用的 apprise 通知器。")
        

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
    elif event == 'komga.delete':
        title = "Komga 书籍已删除"
        message_list = [
            f"书籍ID: {data.get('id')}",
            f"系列ID: {data.get('seriesId')}",
            f"书库ID: {data.get('libraryId')}"
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
    komga_events = {
        'ThumbnailBookAdded': 'komga.new',
        'BookDeleted': 'komga.delete'
    }
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
            if event_type in komga_events:
                book_id = event['data'].get('bookId')
                if book_id and book_id == last_processed_book_id:
                    listener_logger.warning(f"从 SSE Events 连续收到重复的事件: {book_id}, 跳过处理")
                    continue
                
                last_processed_book_id = book_id
                
                book_data = {}
                # For delete events, the book is gone. Don't call the API.
                if event_type == 'BookDeleted':
                    # Construct data from the event payload itself.
                    book_data = {
                        'id': book_id,
                        'seriesId': event['data'].get('seriesId'),
                        'libraryId': event['data'].get('libraryId')
                    }
                # For new books, fetch full details.
                elif event_type == 'ThumbnailBookAdded':
                    book_data = KomgaAPI(komga_server, komga_username, komga_password, logger=listener_logger).get_book(book_id).json()
                
                # Call the unified notify function if book_data is not empty
                if book_data:
                    listener_logger.debug(f"正在为事件 '{komga_events[event_type]}' 分发通知, 数据: {book_data}")
                    notify(event=komga_events[event_type], data=book_data, logger=listener_logger, notification_config=notification_config)

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

        # 检查是否有任何已启用的通知器订阅了任何 'komga.*' 事件
        any_komga_event_configured = any(
            details.get('enable') and any(event.startswith('komga.') for event in details.get('events', []))
            for name, details in notification_config.items() if name != 'enable'
        )

        # 确保所有必要信息都已配置
        if all([komga_server, komga_username, komga_password]) and any_komga_event_configured:
            listen_event(komga_server, komga_username, komga_password, notification_config)
        else:
            if not any_komga_event_configured:
                logger.info("配置文件中未针对任何 'komga.*' 事件进行设置，监听器将不会启动。")
            else:
                logger.warning("Komga 服务器、用户名或密码未配置完整，监听器无法启动。")