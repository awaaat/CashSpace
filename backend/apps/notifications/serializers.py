from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "type",
            "level",
            "title",
            "message",
            "is_read",
            "created_at",
            "metadata",
        ]
        read_only_fields = ["id", "created_at"]