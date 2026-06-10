# apps/notifications/models.py
# Fix: mark_as_read() called save(update_fields=["is_read", "updated_at"]) but
# the Notification model has no `updated_at` field — raises FieldDoesNotExist.
# Removed `updated_at` from update_fields.

import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.cache import cache
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Notification(models.Model):
    """
    High-performance notification model.
    Uses Redis for unread counts to avoid hitting the database on every page load.
    """

    class Type(models.TextChoices):
        PAYMENT_SUCCESS = "PAYMENT_SUCCESS", "Payment Succeeded"
        PAYOUT_COMPLETED = "PAYOUT_COMPLETED", "Payout Completed"
        PAYOUT_FAILED = "PAYOUT_FAILED", "Payout Failed"
        WALLET_ADDED = "WALLET_ADDED", "Wallet Added"
        WALLET_UPDATED = "WALLET_UPDATED", "Wallet Updated"
        WALLET_DELETED = "WALLET_DELETED", "Wallet Deleted"
        VERIFICATION_REMINDER = "VERIFICATION_REMINDER", "Verification Reminder"
        ADMIN_BROADCAST = "ADMIN_BROADCAST", "Admin Broadcast"

    class Level(models.TextChoices):
        SUCCESS = "success", "Success"
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
        db_index=True,
    )
    type = models.CharField(max_length=50, choices=Type.choices, db_index=True)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # NOTE: no updated_at field — do NOT include it in save(update_fields=...)

    # Generic relation to any object (Payment, UserCryptoWallet, etc.)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, null=True, blank=True
    )
    object_id = models.CharField(max_length=255, null=True, blank=True)
    related_object = GenericForeignKey("content_type", "object_id")

    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["type", "created_at"]),
            models.Index(fields=["level"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.title[:50]}"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=["is_read"])
            # cache.decr raises ValueError if key missing — delete is safer
            cache.delete(self._unread_cache_key())

    def save(self, *args, **kwargs):
        created = not self.pk
        super().save(*args, **kwargs)
        if created:
            cache.incr(self._unread_cache_key(), 1)

    def _unread_cache_key(self):
        return f"notif_unread_count_{self.user_id}"

    @classmethod
    def get_unread_count(cls, user):
        """Get unread count from Redis, falling back to database on cache miss."""
        cache_key = f"notif_unread_count_{user.id}"
        count = cache.get(cache_key)
        if count is None:
            count = cls.objects.filter(user=user, is_read=False).count()
            cache.set(cache_key, count, timeout=60 * 5)
        return count

    @classmethod
    def mark_all_read(cls, user):
        """Mark all unread notifications as read in a single query, then clear Redis."""
        updated = cls.objects.filter(user=user, is_read=False).update(is_read=True)
        if updated:
            cache.delete(f"notif_unread_count_{user.id}")
        return updated

    @classmethod
    def create_notification(
        cls,
        user,
        notification_type,
        title,
        message,
        level=None,
        related_object=None,
        metadata=None,
    ):
        """Factory method to create a notification and broadcast via WebSocket."""
        from .utils import broadcast_notification

        level = level or cls.Level.INFO
        obj = cls(
            user=user,
            type=notification_type,
            level=level,
            title=title,
            message=message,
            metadata=metadata or {},
        )
        if related_object:
            obj.content_type = ContentType.objects.get_for_model(related_object)
            obj.object_id = str(related_object.id)
        obj.save()
        broadcast_notification(user.id, obj.to_dict())
        return obj

    def to_dict(self):
        return {
            "id": str(self.id),
            "type": self.type,
            "level": self.level,
            "title": self.title,
            "message": self.message,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat(),
        }