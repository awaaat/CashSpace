# apps/notifications/views.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from .models import Notification
from .serializers import NotificationSerializer
from .filters import NotificationFilter


class IsOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj.user == request.user


class NotificationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user notifications.
    Supports CRUD, bulk mark‑read, and real‑time unread count.
    """
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_class = NotificationFilter
    ordering_fields = ["created_at", "type", "is_read"]
    search_fields = ["title", "message"]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).select_related("user")

    @action(detail=True, methods=["post"])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_as_read()
        notification.refresh_from_db()   # confirm DB write
        return Response({
            "status": "marked as read",
            "is_read": notification.is_read,
            "unread_count": Notification.get_unread_count(request.user),
        })

    @action(detail=False, methods=["post"])
    def mark_all_read(self, request):
        """Mark all unread notifications as read for the current user."""
        updated = Notification.mark_all_read(request.user)
        return Response({"status": "all marked as read", "marked_count": updated})

    @action(detail=False, methods=["get"])
    def unread_count(self, request):
        """Return the number of unread notifications."""
        count = Notification.get_unread_count(request.user)
        return Response({"unread_count": count})

    @action(detail=False, methods=["delete"])
    def delete_all_read(self, request):
        """Delete all read notifications (bulk)."""
        from django.core.cache import cache
        deleted, _ = Notification.objects.filter(user=request.user, is_read=True).delete()
        if deleted:
            cache.delete(f"notif_unread_count_{request.user.id}")
        return Response({"deleted_count": deleted})