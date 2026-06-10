import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Notification
from django.core.cache import cache


class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        if self.user.is_anonymous:
            await self.close()
        else:
            self.group_name = f"user_{self.user.id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.accept()
            # Send current unread count immediately
            await self.send_unread_count()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("action")
        if action == "mark_read":
            notification_id = data.get("id")
            if notification_id:
                await self.mark_notification_read(notification_id)
                await self.send_unread_count()

    async def send_unread_count(self):
        count = await self.get_unread_count()
        await self.send(text_data=json.dumps({"type": "unread_count", "count": count}))

    @database_sync_to_async
    def get_unread_count(self):
        return Notification.get_unread_count(self.user)

    @database_sync_to_async
    def mark_notification_read(self, notification_id):
        try:
            notification = Notification.objects.get(id=notification_id, user=self.user)
            notification.mark_as_read()
            return True
        except Notification.DoesNotExist:
            return False

    async def send_notification(self, event):
        """Called when a new notification is broadcast to the group."""
        await self.send(text_data=json.dumps(event["data"]))
        await self.send_unread_count()