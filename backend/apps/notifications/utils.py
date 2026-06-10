from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def broadcast_notification(user_id, notification_data):
    """
    Send a real‑time notification to a specific user via WebSocket.
    """
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{user_id}",
        {"type": "send_notification", "data": notification_data},
    )