# backend/apps/merchants/admin.py
from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone

from .models import (
    Merchant, Product, CustomerCheckout,
    PostPaymentAction, MerchantAPIKey, WebhookDeliveryLog,
)


# ── Inline: Products inside Merchant ─────────────────────────────────────────

class ProductInline(admin.TabularInline):
    model = Product
    extra = 0
    fields = ["name", "slug", "product_type", "price_usd", "is_active", "purchase_count_display"]
    readonly_fields = ["slug", "purchase_count_display"]
    show_change_link = True

    def purchase_count_display(self, obj):
        return obj.purchase_count if obj.pk else "—"
    purchase_count_display.short_description = "Sales"


# ── Inline: PostPaymentActions inside Product ─────────────────────────────────

class PostPaymentActionInline(admin.TabularInline):
    model = PostPaymentAction
    extra = 0
    fields = ["action_type", "priority", "is_active", "config"]
    ordering = ["priority"]


# ── Inline: API Keys inside Merchant ─────────────────────────────────────────

class MerchantAPIKeyInline(admin.StackedInline):
    model = MerchantAPIKey
    extra = 0
    can_delete = False
    readonly_fields = [
        "test_publishable_key", "test_secret_key_prefix", "test_key_rotated_at",
        "live_publishable_key", "live_secret_key_prefix", "live_key_rotated_at",
        "is_test_mode", "created_at", "updated_at",
    ]
    fields = [
        "is_test_mode",
        "test_publishable_key", "test_secret_key_prefix", "test_key_rotated_at",
        "live_publishable_key", "live_secret_key_prefix", "live_key_rotated_at",
    ]
    verbose_name = "API Keys"
    verbose_name_plural = "API Keys"


# ── Merchant ──────────────────────────────────────────────────────────────────

@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = [
        "business_name", "slug", "user_email",
        "settlement_currency", "settlement_blockchain",
        "commission_rate_display", "mode_badge",
        "is_active", "is_verified",
        "total_sales_display", "created_at",
    ]
    list_filter = [
        "is_active", "is_verified",
        "settlement_blockchain", "settlement_currency",
    ]
    search_fields = ["business_name", "slug", "user__email"]
    readonly_fields = ["id", "slug", "created_at", "updated_at"]
    raw_id_fields = ["user"]
    inlines = [ProductInline, MerchantAPIKeyInline]

    fieldsets = (
        ("Identity", {
            "fields": ("id", "user", "business_name", "slug", "description", "logo_url")
        }),
        ("Settlement", {
            "fields": (
                "settlement_blockchain", "settlement_currency",
                "settlement_wallet_address",
            )
        }),
        ("Commission", {
            "fields": ("commission_rate_override",),
            "description": "Leave blank to use the global CASHSPACE_COMMISSION_RATE setting.",
        }),
        ("Status", {
            "fields": ("is_active", "is_verified")
        }),
        ("Webhook", {
            "fields": ("webhook_url", "webhook_secret"),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "Owner"
    user_email.admin_order_field = "user__email"

    def commission_rate_display(self, obj):
        rate = obj.get_effective_commission_rate()
        pct = int(rate * 100)
        if obj.commission_rate_override is not None:
            return format_html('<span style="color:#f0c040;font-weight:600">{}% (custom)</span>', pct)
        return f"{pct}% (global)"
    commission_rate_display.short_description = "Commission"

    def mode_badge(self, obj):
        try:
            if obj.api_keys.is_test_mode:
                return format_html('<span style="background:#fef3c7;color:#d97706;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">TEST</span>')
            return format_html('<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">LIVE</span>')
        except MerchantAPIKey.DoesNotExist:
            return format_html('<span style="color:#9ca3af">—</span>')
    mode_badge.short_description = "Mode"

    def total_sales_display(self, obj):
        return CustomerCheckout.objects.filter(
            product__merchant=obj,
            status=CustomerCheckout.Status.COMPLETED,
            is_test=False,
        ).count()
    total_sales_display.short_description = "Live Sales"


# ── Product ───────────────────────────────────────────────────────────────────

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "name", "merchant_name", "product_type", "price_usd",
        "purchase_count_display", "is_sold_out_display", "is_active", "created_at",
    ]
    list_filter = ["product_type", "is_active", "merchant__is_active"]
    search_fields = ["name", "slug", "merchant__business_name", "merchant__user__email"]
    readonly_fields = ["id", "slug", "created_at", "updated_at"]
    raw_id_fields = ["merchant"]
    inlines = [PostPaymentActionInline]

    fieldsets = (
        ("Identity", {
            "fields": ("id", "merchant", "name", "slug", "description")
        }),
        ("Pricing", {
            "fields": ("product_type", "price_usd", "min_price_usd")
        }),
        ("Checkout fields", {
            "fields": (
                "collect_telegram", "collect_discord",
                "collect_phone", "collect_custom_field",
            )
        }),
        ("Limits & redirect", {
            "fields": ("max_purchases", "success_redirect_url", "is_active")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def merchant_name(self, obj):
        return obj.merchant.business_name
    merchant_name.short_description = "Merchant"
    merchant_name.admin_order_field = "merchant__business_name"

    def purchase_count_display(self, obj):
        return obj.purchase_count
    purchase_count_display.short_description = "Sales"

    def is_sold_out_display(self, obj):
        if obj.is_sold_out:
            return format_html('<span style="color:#ef4444;font-weight:600">Sold out</span>')
        return format_html('<span style="color:#22c55e">Available</span>')
    is_sold_out_display.short_description = "Stock"


# ── CustomerCheckout ──────────────────────────────────────────────────────────

@admin.register(CustomerCheckout)
class CustomerCheckoutAdmin(admin.ModelAdmin):
    list_display = [
        "email", "product_name", "merchant_name", "amount_usd",
        "mode_badge", "status", "automation_triggered",
        "payment_status_display", "created_at",
    ]
    list_filter = [
        "status", "is_test", "automation_triggered",
        "product__merchant__business_name",
    ]
    search_fields = [
        "email", "full_name", "telegram_username",
        "discord_username", "product__name", "product__merchant__business_name",
    ]
    readonly_fields = [
        "id", "product", "payment", "email", "amount_usd", "is_test",
        "status", "automation_triggered", "automation_triggered_at",
        "automation_error", "ip_address", "user_agent", "created_at", "updated_at",
    ]
    ordering = ["-created_at"]

    fieldsets = (
        ("Buyer identity", {
            "fields": (
                "id", "product", "email", "full_name",
                "telegram_username", "discord_username",
                "phone_number", "custom_field_value",
            )
        }),
        ("Payment", {
            "fields": ("payment", "amount_usd", "is_test", "status")
        }),
        ("Automation", {
            "fields": (
                "automation_triggered", "automation_triggered_at", "automation_error"
            )
        }),
        ("Meta", {
            "fields": ("ip_address", "user_agent", "metadata", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def product_name(self, obj):
        return obj.product.name
    product_name.short_description = "Product"

    def merchant_name(self, obj):
        return obj.product.merchant.business_name
    merchant_name.short_description = "Merchant"

    def mode_badge(self, obj):
        if obj.is_test:
            return format_html('<span style="background:#fef3c7;color:#d97706;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">TEST</span>')
        return format_html('<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">LIVE</span>')
    mode_badge.short_description = "Mode"

    def payment_status_display(self, obj):
        if not obj.payment:
            return format_html('<span style="color:#6b7280">—</span>')
        colors = {
            "FILLED": "#22c55e", "OPEN": "#3b82f6",
            "PENDING": "#6b7280", "FAILED": "#ef4444", "CANCELLED": "#6b7280",
        }
        color = colors.get(obj.payment.status, "#6b7280")
        return format_html(
            '<span style="color:{};font-weight:600">{}</span>',
            color, obj.payment.status,
        )
    payment_status_display.short_description = "Payment"

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


# ── PostPaymentAction ─────────────────────────────────────────────────────────

@admin.register(PostPaymentAction)
class PostPaymentActionAdmin(admin.ModelAdmin):
    list_display = [
        "product_name", "action_type", "priority", "is_active", "created_at",
    ]
    list_filter = ["action_type", "is_active"]
    search_fields = ["product__name", "product__merchant__business_name"]
    readonly_fields = ["id", "created_at", "updated_at"]
    raw_id_fields = ["product"]

    def product_name(self, obj):
        return obj.product.name
    product_name.short_description = "Product"


# ── MerchantAPIKey ────────────────────────────────────────────────────────────

@admin.register(MerchantAPIKey)
class MerchantAPIKeyAdmin(admin.ModelAdmin):
    list_display = [
        "merchant_name", "mode_badge",
        "test_publishable_key_short", "live_publishable_key_short",
        "test_key_rotated_at", "live_key_rotated_at", "created_at",
    ]
    list_filter = ["is_test_mode"]
    search_fields = [
        "merchant__business_name", "merchant__slug",
        "test_publishable_key", "live_publishable_key",
    ]
    readonly_fields = [
        "merchant",
        "test_publishable_key", "test_secret_key_prefix", "test_secret_key_hash",
        "test_key_rotated_at",
        "live_publishable_key", "live_secret_key_prefix", "live_secret_key_hash",
        "live_key_rotated_at",
        "created_at", "updated_at",
    ]
    raw_id_fields = ["merchant"]

    fieldsets = (
        ("Merchant", {
            "fields": ("merchant", "is_test_mode"),
        }),
        ("Test Keys", {
            "fields": (
                "test_publishable_key",
                "test_secret_key_prefix",
                "test_secret_key_hash",
                "test_key_rotated_at",
            ),
            "description": "Secret key hash is stored — raw key not recoverable from here.",
        }),
        ("Live Keys", {
            "fields": (
                "live_publishable_key",
                "live_secret_key_prefix",
                "live_secret_key_hash",
                "live_key_rotated_at",
            ),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def merchant_name(self, obj):
        return obj.merchant.business_name
    merchant_name.short_description = "Merchant"
    merchant_name.admin_order_field = "merchant__business_name"

    def mode_badge(self, obj):
        if obj.is_test_mode:
            return format_html('<span style="background:#fef3c7;color:#d97706;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">TEST</span>')
        return format_html('<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">LIVE</span>')
    mode_badge.short_description = "Mode"

    def test_publishable_key_short(self, obj):
        return f"{obj.test_publishable_key[:24]}..."
    test_publishable_key_short.short_description = "Test PK"

    def live_publishable_key_short(self, obj):
        return f"{obj.live_publishable_key[:24]}..."
    live_publishable_key_short.short_description = "Live PK"

    def has_add_permission(self, request):
        return False  # always auto-created via signal


# ── WebhookDeliveryLog ────────────────────────────────────────────────────────

@admin.register(WebhookDeliveryLog)
class WebhookDeliveryLogAdmin(admin.ModelAdmin):
    list_display = [
        "merchant_name", "event_type", "status_badge",
        "response_status_code", "attempt_number",
        "duration_ms", "mode_badge", "created_at",
    ]
    list_filter = ["status", "event_type", "is_test"]
    search_fields = [
        "merchant__business_name", "endpoint_url",
        "checkout__email",
    ]
    readonly_fields = [
        "merchant", "checkout", "event_type", "is_test",
        "endpoint_url", "request_body", "request_headers",
        "response_status_code", "response_body", "duration_ms",
        "status", "attempt_number", "next_retry_at", "error_message",
        "created_at", "updated_at",
    ]
    ordering = ["-created_at"]

    fieldsets = (
        ("Event", {
            "fields": ("merchant", "checkout", "event_type", "is_test"),
        }),
        ("Request", {
            "fields": ("endpoint_url", "request_body", "request_headers"),
        }),
        ("Response", {
            "fields": (
                "response_status_code", "response_body",
                "duration_ms", "error_message",
            ),
        }),
        ("Delivery status", {
            "fields": ("status", "attempt_number", "next_retry_at"),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
        }),
    )

    def merchant_name(self, obj):
        return obj.merchant.business_name
    merchant_name.short_description = "Merchant"
    merchant_name.admin_order_field = "merchant__business_name"

    def status_badge(self, obj):
        colors = {
            "success":   ("d1fae5", "065f46"),
            "failed":    ("fee2e2", "991b1b"),
            "retrying":  ("fef3c7", "d97706"),
            "exhausted": ("fee2e2", "991b1b"),
            "pending":   ("f1f5f9", "475569"),
        }
        bg, fg = colors.get(obj.status, ("f1f5f9", "475569"))
        return format_html(
            '<span style="background:#{};color:#{};padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">{}</span>',
            bg, fg, obj.status.upper(),
        )
    status_badge.short_description = "Status"

    def mode_badge(self, obj):
        if obj.is_test:
            return format_html('<span style="background:#fef3c7;color:#d97706;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">TEST</span>')
        return format_html('<span style="background:#d1fae5;color:#065f46;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:700">LIVE</span>')
    mode_badge.short_description = "Mode"

    def has_add_permission(self, request):
        return False  # append-only, created by tasks only

    def has_delete_permission(self, request, obj=None):
        return False  # immutable audit log