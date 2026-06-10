# apps/payments/admin.py
# Updated for multi‑chain / multi‑currency Payment model.

from django.contrib import admin
from django.utils.html import format_html

from .models import Payment, WebhookEvent, UserCryptoWallet


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user_email",
        "amount_usd",
        "commission_usd",
        "payout_crypto_amount_display",
        "blockchain_code",
        "currency_code",
        "status",
        "payout_status_display",
        "created_at",
    ]
    list_filter = [
        "status",
        "payout_status",
        "blockchain_code",
        "currency_code",
    ]
    search_fields = [
        "user__email",
        "payram_reference_id",
        "destination_wallet",
        "payram_payout_id",
    ]
    readonly_fields = [
        "id",
        "user",
        "amount_usd",
        "commission_rate",
        "commission_usd",
        "payout_usd_equivalent",
        "payout_crypto_amount",
        "exchange_rate_usd_to_crypto",
        "blockchain_code",
        "currency_code",
        "destination_wallet",
        "payram_reference_id",
        "payram_payment_url",
        "payram_raw_status",
        "payram_payout_id",
        "payout_initiated_at",
        "payout_completed_at",
        "payout_error",
        "payment_method",
        "payment_method_details",
        "last_webhook_at",
        "webhook_count",
        "error_message",
        "notes",
        "created_at",
        "updated_at",
    ]
    ordering = ["-created_at"]

    fieldsets = (
        ("Payment", {
            "fields": (
                "id", "user", "amount_usd", "commission_rate",
                "commission_usd", "payout_usd_equivalent",
                "payout_crypto_amount", "exchange_rate_usd_to_crypto",
                "blockchain_code", "currency_code", "destination_wallet",
            )
        }),
        ("PayRam Payment", {
            "fields": (
                "payram_reference_id", "payram_payment_url",
                "status", "payram_raw_status",
            )
        }),
        ("PayRam Payout", {
            "fields": (
                "payram_payout_id", "payout_status",
                "payout_initiated_at", "payout_completed_at", "payout_error",
            )
        }),
        ("Payment Method", {
            "fields": ("payment_method", "payment_method_details"),
        }),
        ("Webhooks", {
            "fields": ("last_webhook_at", "webhook_count"),
        }),
        ("Errors & Notes", {
            "fields": ("error_message", "notes"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "User"

    def payout_crypto_amount_display(self, obj):
        if obj.payout_crypto_amount:
            return f"{obj.payout_crypto_amount:.8f} {obj.currency_code}"
        return "-"
    payout_crypto_amount_display.short_description = "Crypto sent"

    def payout_status_display(self, obj):
        colors = {
            "NOT_INITIATED": "#999",
            "pending-approval": "#f0ad4e",
            "approved": "#5bc0de",
            "completed": "#5cb85c",
            "failed": "#d9534f",
        }
        color = colors.get(obj.payout_status, "#999")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_payout_status_display(),
        )
    payout_status_display.short_description = "Payout Status"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "event_type",
        "payram_reference_id",
        "signature_valid",
        "processed",
    ]
    list_filter = ["signature_valid", "processed", "event_type"]
    search_fields = ["payram_reference_id", "event_type"]
    readonly_fields = [
        "id",
        "payment",
        "payram_reference_id",
        "event_type",
        "payload",
        "signature_valid",
        "processed",
        "error",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(UserCryptoWallet)
class UserCryptoWalletAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "user_email",
        "blockchain_code",
        "currency_code",
        "wallet_address_short",
        "is_default",
        "is_active",
        "created_at",
    ]
    list_filter = ["blockchain_code", "currency_code", "is_default", "is_active"]
    search_fields = ["user__email", "wallet_address", "label"]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["user"]

    fieldsets = (
        (None, {
            "fields": ("user", "blockchain_code", "currency_code", "wallet_address", "label")
        }),
        ("Status", {
            "fields": ("is_active", "is_default")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "User"
    user_email.admin_order_field = "user__email"

    def wallet_address_short(self, obj):
        addr = obj.wallet_address
        if len(addr) > 20:
            return f"{addr[:12]}...{addr[-8:]}"
        return addr
    wallet_address_short.short_description = "Wallet address"

    def has_delete_permission(self, request, obj=None):
        return True  # Allow deletion via admin for safety