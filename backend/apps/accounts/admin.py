# apps/accounts/admin.py
# Updated for multi‑currency (removed BTC‑only fields, added crypto wallet info)

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse

from .models import AuditLog, EmailVerificationToken, PasswordResetToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        "email", "full_name", "role", "is_active", "is_email_verified",
        "wallet_count_display", "last_login", "date_joined",
    ]
    list_filter = ["role", "is_active", "is_email_verified", "is_kyc_verified"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["-date_joined"]
    readonly_fields = ["id", "date_joined", "last_login", "last_login_ip"]

    fieldsets = (
        ("Identity", {"fields": ("id", "email", "first_name", "last_name", "phone_number", "avatar")}),
        ("Password", {"fields": ("password",)}),
        ("Role & Status", {"fields": ("role", "is_active", "is_staff", "is_superuser", "is_email_verified", "is_kyc_verified")}),
        ("Security", {"fields": ("failed_login_attempts", "locked_until", "last_login", "last_login_ip")}),
        ("Permissions", {"fields": ("groups", "user_permissions")}),
        ("Dates", {"fields": ("date_joined",)}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "role", "password1", "password2"),
        }),
    )

    def wallet_count_display(self, obj):
        count = obj.crypto_wallets.filter(is_active=True).count()
        if count == 0:
            return format_html('<span style="color: #999;">—</span>')
        # Link to a filtered view in the UserCryptoWallet admin (optional)
        return format_html(
            '<a href="{}?user__id__exact={}">{} wallet(s)</a>',
            reverse("admin:payments_usercryptowallet_changelist"),
            obj.id,
            count,
        )
    wallet_count_display.short_description = "Crypto Wallets"

    def get_queryset(self, request):
        # prefetch wallets to avoid N+1
        return super().get_queryset(request).prefetch_related("crypto_wallets")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "user", "action", "ip_address"]
    list_filter = ["action"]
    search_fields = ["user__email", "ip_address"]
    readonly_fields = ["id", "user", "action", "ip_address", "user_agent", "metadata", "created_at"]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at", "expires_at", "used_at"]
    readonly_fields = ["id", "user", "token", "created_at", "expires_at", "used_at"]


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at", "expires_at", "used_at"]
    readonly_fields = ["id", "user", "token", "created_at", "expires_at", "used_at"]