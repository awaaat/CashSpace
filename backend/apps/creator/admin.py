"""
apps/creator/admin.py
=====================
Django admin configuration for the creator app.

Provides admin interface for:
  - CreatorProfile (user profiles)
  - PayableAsset (all assets across creators)
  - CreatorSale (sales records)
  - CreatorAffiliateProgram
  - CreatorDiscountCode

Includes inline management, custom actions (duplicate asset, mark sale as paid),
and useful filters/search fields.
"""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone

from .models import (
    CreatorProfile,
    PayableAsset,
    CreatorSale,
    CreatorAffiliateProgram,
    CreatorDiscountCode,
)


# ----------------------------------------------------------------------
# Inlines
# ----------------------------------------------------------------------
class PayableAssetInline(admin.TabularInline):
    """Inline for assets under a creator profile."""
    model = PayableAsset
    extra = 0
    fields = ["title", "asset_type", "price_usd", "is_active", "created_at"]
    readonly_fields = ["created_at"]
    show_change_link = True


class CreatorSaleInline(admin.TabularInline):
    """Inline for sales under an asset."""
    model = CreatorSale
    extra = 0
    fields = ["buyer_email", "amount_usd", "status", "created_at"]
    readonly_fields = ["buyer_email", "amount_usd", "status", "created_at"]
    show_change_link = True


class CreatorDiscountCodeInline(admin.TabularInline):
    """Inline for discount codes under an asset."""
    model = CreatorDiscountCode
    extra = 0
    fields = ["code", "discount_type", "discount_value", "max_uses", "used_count", "is_active"]
    readonly_fields = ["used_count"]


# ----------------------------------------------------------------------
# CreatorProfile Admin
# ----------------------------------------------------------------------
@admin.register(CreatorProfile)
class CreatorProfileAdmin(admin.ModelAdmin):
    list_display = [
        "id", "user_email", "display_name", "total_sales", "total_revenue_usd",
        "is_verified", "created_at"
    ]
    list_filter = ["is_verified", "created_at"]
    search_fields = ["user__email", "display_name", "user__first_name", "user__last_name"]
    readonly_fields = ["id", "created_at", "updated_at", "total_sales", "total_revenue_usd"]
    raw_id_fields = ["user"]
    inlines = [PayableAssetInline]
    fieldsets = (
        ("Identity", {
            "fields": ("id", "user", "display_name", "bio", "avatar_url", "cover_image_url")
        }),
        ("Social", {
            "fields": ("website", "twitter_handle", "telegram_handle")
        }),
        ("Payout Settings", {
            "fields": ("custom_payout_wallet", "custom_payout_blockchain", "custom_payout_currency")
        }),
        ("Commission", {
            "fields": ("commission_rate_override",)
        }),
        ("Verification & Limits", {
            "fields": ("is_verified", "verification_docs", "max_assets", "max_monthly_sales")
        }),
        ("Statistics", {
            "fields": ("total_views", "total_sales", "total_revenue_usd")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "User"
    user_email.admin_order_field = "user__email"


# ----------------------------------------------------------------------
# PayableAsset Admin
# ----------------------------------------------------------------------
@admin.register(PayableAsset)
class PayableAssetAdmin(admin.ModelAdmin):
    list_display = [
        "title", "creator_email", "asset_type", "price_usd", "total_sales_count",
        "is_active", "is_sold_out_flag", "created_at"
    ]
    list_filter = ["asset_type", "pricing_type", "is_active", "created_at"]
    search_fields = ["title", "slug", "creator__user__email", "description"]
    readonly_fields = [
        "id", "slug", "view_count", "conversion_count", "revenue_usd",
        "total_sales_count", "created_at", "updated_at"
    ]
    raw_id_fields = ["creator"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [CreatorSaleInline, CreatorDiscountCodeInline]
    actions = ["duplicate_asset", "deactivate_selected", "activate_selected"]

    fieldsets = (
        ("Basic Info", {
            "fields": ("id", "creator", "title", "slug", "description", "thumbnail_url", "video_preview_url")
        }),
        ("Asset Configuration", {
            "fields": ("asset_type", "unlock_value", "unlock_config")
        }),
        ("Pricing", {
            "fields": ("pricing_type", "price_usd", "min_price_usd", "max_price_usd", "price_tiers")
        }),
        ("Subscription (if applicable)", {
            "fields": ("subscription_interval_days", "subscription_trial_days", "subscription_max_cycles"),
            "classes": ("collapse",)
        }),
        ("Access & Token Settings", {
            "fields": ("access_duration_value", "access_duration_unit", "token_expires_hours", "token_max_uses")
        }),
        ("Limits", {
            "fields": ("is_active", "max_sales", "max_sales_per_buyer", "allowed_countries", "require_captcha")
        }),
        ("Settlement", {
            "fields": ("custom_settlement_wallet", "custom_settlement_blockchain", "custom_settlement_currency")
        }),
        ("Post-Purchase", {
            "fields": ("success_message", "success_redirect_url", "send_welcome_email", "custom_email_template")
        }),
        ("Webhook", {
            "fields": ("webhook_url", "webhook_secret"),
            "classes": ("collapse",)
        }),
        ("Statistics", {
            "fields": ("view_count", "conversion_count", "revenue_usd", "total_sales_count")
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def creator_email(self, obj):
        return obj.creator.user.email
    creator_email.short_description = "Creator"
    creator_email.admin_order_field = "creator__user__email"

    def total_sales_count(self, obj):
        return obj.sales.filter(status=CreatorSale.Status.COMPLETED).count()
    total_sales_count.short_description = "Sales"

    def is_sold_out_flag(self, obj):
        if obj.is_sold_out:
            return format_html('<span style="color:#ef4444;">Sold out</span>')
        return format_html('<span style="color:#22c55e;">Available</span>')
    is_sold_out_flag.short_description = "Stock"

    def duplicate_asset(self, request, queryset):
        for asset in queryset:
            new_asset = asset
            new_asset.pk = None
            new_asset.title = f"{asset.title} (copy)"
            new_asset.slug = ""
            new_asset.view_count = 0
            new_asset.conversion_count = 0
            new_asset.revenue_usd = 0
            new_asset.save()
            self.message_user(request, f"Duplicated {asset.title}")
    duplicate_asset.short_description = "Duplicate selected assets"

    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} asset(s) deactivated.")
    deactivate_selected.short_description = "Deactivate selected"

    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} asset(s) activated.")
    activate_selected.short_description = "Activate selected"


# ----------------------------------------------------------------------
# CreatorSale Admin
# ----------------------------------------------------------------------
@admin.register(CreatorSale)
class CreatorSaleAdmin(admin.ModelAdmin):
    list_display = [
        "id", "asset_title", "buyer_email", "amount_usd", "net_usd",
        "status_badge", "created_at", "paid_at"
    ]
    list_filter = ["status", "created_at", "paid_at"]
    search_fields = ["buyer_email", "buyer_name", "asset__title", "access_token"]
    readonly_fields = [
        "id", "asset", "buyer_email", "buyer_name", "amount_usd", "commission_usd",
        "net_usd", "access_token", "payment_id", "payout_id", "metadata",
        "created_at", "updated_at"
    ]
    raw_id_fields = ["asset"]
    actions = ["mark_as_paid", "resend_access_email"]

    fieldsets = (
        ("Sale Info", {
            "fields": ("id", "asset", "buyer_email", "buyer_name", "amount_usd", "commission_usd", "net_usd")
        }),
        ("Status", {
            "fields": ("status", "paid_at", "payment_id", "payout_id")
        }),
        ("Access", {
            "fields": ("access_token",)
        }),
        ("Metadata", {
            "fields": ("metadata",),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def asset_title(self, obj):
        return obj.asset.title
    asset_title.short_description = "Asset"
    asset_title.admin_order_field = "asset__title"

    def status_badge(self, obj):
        colors = {
            CreatorSale.Status.PENDING: "#6b7280",
            CreatorSale.Status.PROCESSING: "#f59e0b",
            CreatorSale.Status.COMPLETED: "#22c55e",
            CreatorSale.Status.REFUNDED: "#ef4444",
            CreatorSale.Status.FAILED: "#ef4444",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html('<span style="color:{}; font-weight:600;">{}</span>', color, obj.get_status_display())
    status_badge.short_description = "Status"

    def mark_as_paid(self, request, queryset):
        updated = 0
        for sale in queryset:
            if sale.status != CreatorSale.Status.COMPLETED:
                sale.status = CreatorSale.Status.COMPLETED
                sale.paid_at = timezone.now()
                sale.save(update_fields=["status", "paid_at"])
                updated += 1
        self.message_user(request, f"{updated} sale(s) marked as paid.")
    mark_as_paid.short_description = "Mark selected sales as paid"

    def resend_access_email(self, request, queryset):
        from .tasks import send_access_email
        sent = 0
        for sale in queryset:
            if sale.access_token:
                send_access_email.delay(str(sale.id))
                sent += 1
        self.message_user(request, f"Access email re-queued for {sent} sale(s).")
    resend_access_email.short_description = "Resend access email"


# ----------------------------------------------------------------------
# CreatorAffiliateProgram Admin
# ----------------------------------------------------------------------
@admin.register(CreatorAffiliateProgram)
class CreatorAffiliateProgramAdmin(admin.ModelAdmin):
    list_display = ["asset_title", "commission_percent", "is_active", "cookie_days"]
    list_filter = ["is_active"]
    search_fields = ["asset__title", "asset__creator__user__email"]
    raw_id_fields = ["asset"]
    readonly_fields = ["id"]

    def asset_title(self, obj):
        return obj.asset.title
    asset_title.short_description = "Asset"


# ----------------------------------------------------------------------
# CreatorDiscountCode Admin
# ----------------------------------------------------------------------
@admin.register(CreatorDiscountCode)
class CreatorDiscountCodeAdmin(admin.ModelAdmin):
    list_display = [
        "code", "asset_title", "discount_display", "max_uses", "used_count",
        "valid_from", "valid_to", "is_active"
    ]
    list_filter = ["discount_type", "is_active", "valid_from", "valid_to"]
    search_fields = ["code", "asset__title"]
    raw_id_fields = ["asset"]
    readonly_fields = ["id", "used_count"]

    fieldsets = (
        ("Basic", {
            "fields": ("asset", "code", "discount_type", "discount_value")
        }),
        ("Usage Limits", {
            "fields": ("max_uses", "used_count")
        }),
        ("Validity Period", {
            "fields": ("valid_from", "valid_to", "is_active")
        }),
    )

    def asset_title(self, obj):
        return obj.asset.title
    asset_title.short_description = "Asset"

    def discount_display(self, obj):
        if obj.discount_type == "percent":
            return f"{obj.discount_value}%"
        return f"${obj.discount_value}"
    discount_display.short_description = "Discount"