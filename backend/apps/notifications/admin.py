# apps/notifications/admin.py
# Fix: added missing `from django.core.cache import cache` — caused NameError
# in the `mark_as_read` admin action.

from django.contrib import admin
from django.core.cache import cache          # ← was missing
from django.utils.html import format_html
from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "title_short", "type", "level", "is_read", "created_at"]
    list_filter = ["type", "level", "is_read", "created_at"]
    search_fields = ["user__email", "title", "message"]
    readonly_fields = ["id", "created_at"]
    raw_id_fields = ["user"]
    actions = ["mark_as_read", "delete_selected"]

    def title_short(self, obj):
        return obj.title[:50] + "…" if len(obj.title) > 50 else obj.title
    title_short.short_description = "Title"

    def mark_as_read(self, request, queryset):
        updated = queryset.update(is_read=True)
        # Clear Redis caches for all affected users
        user_ids = queryset.values_list("user_id", flat=True).distinct()
        for user_id in user_ids:
            cache.delete(f"notif_unread_count_{user_id}")
        self.message_user(request, f"{updated} notifications marked as read.")
    mark_as_read.short_description = "Mark selected as read"