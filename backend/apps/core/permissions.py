from rest_framework.permissions import BasePermission, IsAdminUser


class IsOwnerOrAdmin(BasePermission):
    """Allow access to the object owner or any admin."""

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        owner = getattr(obj, "user", None) or getattr(obj, "owner", None)
        return owner == request.user


class IsVerifiedUser(BasePermission):
    """Allow access only to users who have verified their email."""

    message = "Email verification required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_email_verified
        )


class IsActiveUser(BasePermission):
    """Block suspended/deactivated accounts."""

    message = "Your account has been suspended. Contact support."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
        )