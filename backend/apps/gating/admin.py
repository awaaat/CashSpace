"""
apps/gating/admin.py
====================
Django admin configuration for the gating app.

Provides full CRUD and monitoring capabilities for:
  - GatedAsset (with inline AccessGrants and DiscountCodes)
  - AccessGrant (with inline AccessToken and AccessLogs)
  - AccessToken
  - AccessLog
  - DiscountCode
  - AffiliateClick
  - EmbedToken

All views include search, filters, readonly audit fields, and custom actions
(e.g., revoke access, resend tokens, bulk mark as refunded).
"""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Count, Sum
from django.contrib.admin import SimpleListFilter

from .models import (
    GatedAsset,
    AccessGrant,
    AccessToken,
    AccessLog,
    DiscountCode,
    AffiliateClick,
    EmbedToken,
)


# ----------------------------------------------------------------------
# Inlines
# ----------------------------------------------------------------------
class AccessGrantInline(admin.TabularInline):
    """Inline view of AccessGrants directly under a GatedAsset."""
    model = AccessGrant
    extra = 0
    fields = [
        "email", "full_name", "amount_usd", "status",
        "unlock_delivered", "created_at", "access_token_link",
    ]
    readonly_fields = [
        "email", "full_name", "amount_usd", "status",
        "unlock_delivered", "created_at", "access_token_link",
    ]
    can_delete = False
    show_change_link = True
    ordering = ["-created_at"]

    def access_token_link(self, obj):
        if hasattr(obj, "access_token"):
            url = reverse("admin:gating_accesstoken_change", args=[obj.access_token.id])
            return format_html('<a href="{}">{}</a>', url, obj.access_token.token[:12])
        return "—"
    access_token_link.short_description = "Access Token"


class DiscountCodeInline(admin.TabularInline):
    """Inline for discount codes attached to an asset."""
    model = DiscountCode.assets.through
    verbose_name = "Discount Code"
    verbose_name_plural = "Discount Codes (Linked to this Asset)"
    extra = 0
    fields = ["discountcode", "get_code", "get_uses"]
    readonly_fields = ["get_code", "get_uses"]

    def get_code(self, obj):
        return obj.discountcode.code
    get_code.short_description = "Code"

    def get_uses(self, obj):
        return f"{obj.discountcode.used_count} / {obj.discountcode.max_uses}"
    get_uses.short_description = "Usage"


class AccessTokenInline(admin.StackedInline):
    """Inline for AccessToken under AccessGrant."""
    model = AccessToken
    extra = 0
    fields = ["token", "expires_at", "use_count", "max_uses", "last_used_at"]
    readonly_fields = ["token", "use_count", "last_used_at"]
    can_delete = False
    show_change_link = True


class AccessLogInline(admin.TabularInline):
    model = AccessLog
    extra = 0
    fields = ["action", "success", "ip_address", "created_at"]
    readonly_fields = fields
    can_delete = False
    ordering = ["-created_at"]


# ----------------------------------------------------------------------
# Custom Filters
# ----------------------------------------------------------------------
class GrantStatusFilter(SimpleListFilter):
    title = "grant status"
    parameter_name = "grant_status"
    default_value = None

    def lookups(self, request, model_admin):
        return [
            ("active", "Active (Granted & Not Expired)"),
            ("expired", "Expired"),
            ("pending", "Pending Payment"),
            ("revoked", "Revoked"),
        ]

    def queryset(self, request, queryset):
        now = timezone.now()
        if self.value() == "active":
            return queryset.filter(
                status=AccessGrant.Status.GRANTED,
            ).exclude(
                access_expires_at__lt=now
            )
        if self.value() == "expired":
            return queryset.filter(
                status=AccessGrant.Status.GRANTED,
                access_expires_at__lt=now
            )
        if self.value() == "pending":
            return queryset.exclude(status=AccessGrant.Status.GRANTED)
        if self.value() == "revoked":
            return queryset.filter(status=AccessGrant.Status.REVOKED)
        return queryset


class AssetTypeFilter(admin.SimpleListFilter):
    title = "asset type"
    parameter_name = "asset_type"
    def lookups(self, request, model_admin):
        return GatedAsset.AssetType.choices
    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(asset_type=self.value())
        return queryset


# ----------------------------------------------------------------------
# GatedAsset Admin
# ----------------------------------------------------------------------
@admin.register(GatedAsset)
class GatedAssetAdmin(admin.ModelAdmin):
    list_display = [
        "title", "owner_email", "asset_type_badge", "effective_price",
        "grant_count", "revenue_usd", "is_active", "is_sold_out_flag", "created_at"
    ]
    list_filter = [
        AssetTypeFilter,
        "pricing_type",
        "is_active",
        "created_at",
    ]
    search_fields = ["title", "slug", "owner__email", "description"]
    readonly_fields = ["id", "slug", "grant_count", "revenue_usd", "created_at", "updated_at"]
    raw_id_fields = ["owner", "merchant"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [AccessGrantInline, DiscountCodeInline]
    actions = ["duplicate_asset", "deactivate_selected", "activate_selected"]

    fieldsets = (
        ("Identity", {
            "fields": ("id", "owner", "merchant", "title", "slug", "description", "thumbnail_url", "video_preview_url")
        }),
        ("Asset Details", {
            "fields": ("asset_type", "unlock_value", "unlock_config")
        }),
        ("Pricing", {
            "fields": ("pricing_type", "price_usd", "min_price_usd", "max_price_usd", "price_tiers")
        }),
        ("Subscription (if applicable)", {
            "fields": ("subscription_interval_value", "subscription_interval_unit", "subscription_trial_days", "subscription_max_cycles"),
            "classes": ("collapse",)
        }),
        ("Access Duration", {
            "fields": ("grant_duration_value", "grant_duration_unit")
        }),
        ("Settlement", {
            "fields": ("settlement_blockchain", "settlement_currency", "settlement_wallet_address")
        }),
        ("Token Settings", {
            "fields": ("token_expires_after_grant_value", "token_max_uses", "token_requires_email_verification")
        }),
        ("Limits & Restrictions", {
            "fields": ("is_active", "max_grants", "max_grants_per_email", "allowed_countries", "blocked_countries", "require_captcha")
        }),
        ("Referrers & Affiliates", {
            "fields": ("allowed_referrers", "affiliate_commission_percent", "affiliate_cookie_days")
        }),
        ("Discounts & Dynamic Pricing", {
            "fields": ("discount_codes", "dynamic_pricing_enabled", "base_price_usd", "price_multiplier", "demand_window_days"),
            "classes": ("collapse",)
        }),
        ("Advanced Features", {
            "fields": ("steps", "bundled_assets", "nft_gate_contract", "nft_gate_min_balance", "blockchain_network"),
            "classes": ("collapse",)
        }),
        ("Post‑Payment", {
            "fields": ("success_message", "success_redirect_url", "send_welcome_email", "welcome_email_template")
        }),
        ("Webhooks", {
            "fields": ("webhook_url", "webhook_secret"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def owner_email(self, obj):
        return obj.owner.email
    owner_email.short_description = "Owner"
    owner_email.admin_order_field = "owner__email"

    def asset_type_badge(self, obj):
        colors = {
            "url": "#3b82f6",
            "telegram": "#229ED9",
            "discord": "#5865F2",
            "file": "#10b981",
            "api_key": "#f59e0b",
            "embed": "#8b5cf6",
            "webhook": "#ec489a",
            "content": "#6b7280",
        }
        color = colors.get(obj.asset_type, "#6b7280")
        return format_html('<span style="background: {}20; color: {}; padding: 2px 8px; border-radius: 12px;">{}</span>',
                           color, color, obj.get_asset_type_display())
    asset_type_badge.short_description = "Type"

    def effective_price(self, obj):
        if obj.pricing_type == GatedAsset.PricingType.FIXED and obj.price_usd:
            return f"${obj.price_usd}"
        if obj.pricing_type == GatedAsset.PricingType.DONATION:
            return f"${obj.min_price_usd}+ (donation)"
        if obj.pricing_type == GatedAsset.PricingType.TIERED:
            return f"{len(obj.price_tiers)} tiers"
        if obj.pricing_type == GatedAsset.PricingType.SUBSCRIPTION:
            return f"Recurring"
        return "—"
    effective_price.short_description = "Price"

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
            new_asset.save()
            self.message_user(request, f"Duplicated {asset.title}")
    duplicate_asset.short_description = "Duplicate selected asset"

    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} asset(s) deactivated.")
    deactivate_selected.short_description = "Deactivate selected"

    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} asset(s) activated.")
    activate_selected.short_description = "Activate selected"


# ----------------------------------------------------------------------
# AccessGrant Admin
# ----------------------------------------------------------------------
@admin.register(AccessGrant)
class AccessGrantAdmin(admin.ModelAdmin):
    list_display = [
        "id", "email", "asset_title", "amount_usd", "status_badge",
        "access_valid_badge", "unlock_delivered", "created_at", "payment_status_link"
    ]
    list_filter = [
        GrantStatusFilter,
        "status",
        "unlock_delivered",
        "asset__asset_type",
        "created_at",
    ]
    search_fields = ["email", "full_name", "asset__title", "payment__payram_reference_id"]
    readonly_fields = [
        "id", "created_at", "updated_at", "access_token_link", "embed_tokens_link"
    ]
    raw_id_fields = ["asset", "payment"]
    inlines = [AccessTokenInline, AccessLogInline]
    actions = ["resend_access_email", "revoke_selected", "mark_refunded", "export_as_csv"]

    fieldsets = (
        ("Buyer", {
            "fields": ("email", "full_name", "country_code", "ip_address", "user_agent")
        }),
        ("Asset", {
            "fields": ("asset", "selected_tier_index")
        }),
        ("Payment", {
            "fields": ("amount_usd", "payment", "discount_code_used", "discount_amount_usd", "affiliate_code")
        }),
        ("Status & Access", {
            "fields": ("status", "access_expires_at", "unlock_delivered", "unlock_delivered_at", "unlock_error")
        }),
        ("Metadata & Links", {
            "fields": ("metadata", "access_token_link", "embed_tokens_link"),
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
            AccessGrant.Status.INITIATED: "#6b7280",
            AccessGrant.Status.PENDING_EMAIL_VERIFICATION: "#f59e0b",
            AccessGrant.Status.PAYMENT_CREATED: "#3b82f6",
            AccessGrant.Status.GRANTED: "#22c55e",
            AccessGrant.Status.ABANDONED: "#9ca3af",
            AccessGrant.Status.REFUNDED: "#ef4444",
            AccessGrant.Status.REVOKED: "#ef4444",
            AccessGrant.Status.EXPIRED: "#6b7280",
        }
        color = colors.get(obj.status, "#6b7280")
        return format_html('<span style="background: {}20; color: {}; padding: 2px 8px; border-radius: 12px;">{}</span>',
                           color, color, obj.get_status_display())
    status_badge.short_description = "Status"

    def access_valid_badge(self, obj):
        if obj.is_access_valid():
            return format_html('<span style="color:#22c55e;">✓ Active</span>')
        if obj.status == AccessGrant.Status.GRANTED and obj.access_expires_at and timezone.now() > obj.access_expires_at:
            return format_html('<span style="color:#ef4444;">Expired</span>')
        return "—"
    access_valid_badge.short_description = "Access Valid"

    def payment_status_link(self, obj):
        if obj.payment:
            url = reverse("admin:payments_payment_change", args=[obj.payment.id])
            return format_html('<a href="{}">{}</a>', url, obj.payment.status)
        return "—"
    payment_status_link.short_description = "Payment"

    def access_token_link(self, obj):
        if hasattr(obj, "access_token"):
            url = reverse("admin:gating_accesstoken_change", args=[obj.access_token.id])
            return format_html('<a href="{}">{}</a>', url, obj.access_token.token[:16])
        return "—"
    access_token_link.short_description = "Access Token"

    def embed_tokens_link(self, obj):
        count = obj.embed_tokens.count()
        if count:
            return format_html('<a href="{}?grant__id__exact={}">{} token(s)</a>',
                               reverse("admin:gating_embedtoken_changelist"), obj.id, count)
        return "—"
    embed_tokens_link.short_description = "Embed Tokens"

    def resend_access_email(self, request, queryset):
        from .tasks import send_access_grant_email
        sent = 0
        for grant in queryset:
            if grant.status == AccessGrant.Status.GRANTED and hasattr(grant, "access_token"):
                send_access_grant_email.delay(str(grant.id))
                sent += 1
        self.message_user(request, f"Resent access email to {sent} grant(s).")
    resend_access_email.short_description = "Resend access email"

    def revoke_selected(self, request, queryset):
        count = 0
        for grant in queryset:
            if grant.status == AccessGrant.Status.GRANTED:
                grant.revoke()
                count += 1
        self.message_user(request, f"Revoked {count} grant(s).")
    revoke_selected.short_description = "Revoke access"

    def mark_refunded(self, request, queryset):
        updated = queryset.update(status=AccessGrant.Status.REFUNDED)
        self.message_user(request, f"Marked {updated} grant(s) as refunded.")
    mark_refunded.short_description = "Mark as Refunded"

    def export_as_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="access_grants.csv"'
        writer = csv.writer(response)
        writer.writerow(["ID", "Email", "Asset", "Amount USD", "Status", "Created", "Payment ID"])
        for grant in queryset:
            writer.writerow([
                str(grant.id), grant.email, grant.asset.title,
                grant.amount_usd, grant.status, grant.created_at.isoformat(),
                str(grant.payment_id) if grant.payment_id else ""
            ])
        return response
    export_as_csv.short_description = "Export selected to CSV"


# ----------------------------------------------------------------------
# AccessToken Admin
# ----------------------------------------------------------------------
@admin.register(AccessToken)
class AccessTokenAdmin(admin.ModelAdmin):
    list_display = [
        "token_short", "grant_email", "asset_title", "use_count", "max_uses",
        "expires_at", "is_valid_badge", "last_used_at"
    ]
    list_filter = ["max_uses", "expires_at"]
    search_fields = ["token", "grant__email", "grant__asset__title"]
    readonly_fields = ["token", "created_at", "use_count", "last_used_at"]
    raw_id_fields = ["grant"]
    actions = ["invalidate_selected"]

    fieldsets = (
        (None, {
            "fields": ("grant", "token", "expires_at", "max_uses")
        }),
        ("Usage", {
            "fields": ("use_count", "last_used_at", "created_at")
        }),
    )

    def token_short(self, obj):
        return obj.token[:16] + "…"
    token_short.short_description = "Token"

    def grant_email(self, obj):
        return obj.grant.email
    grant_email.short_description = "Buyer"
    grant_email.admin_order_field = "grant__email"

    def asset_title(self, obj):
        return obj.grant.asset.title
    asset_title.short_description = "Asset"

    def is_valid_badge(self, obj):
        if obj.is_valid:
            return format_html('<span style="color:#22c55e;">✓ Valid</span>')
        if obj.is_expired:
            return format_html('<span style="color:#ef4444;">Expired</span>')
        if obj.is_exhausted:
            return format_html('<span style="color:#f59e0b;">Exhausted</span>')
        return format_html('<span style="color:#6b7280;">Invalid</span>')
    is_valid_badge.short_description = "Status"

    def invalidate_selected(self, request, queryset):
        now = timezone.now()
        updated = queryset.update(expires_at=now)
        self.message_user(request, f"Invalidated {updated} token(s).")
    invalidate_selected.short_description = "Invalidate (set expired now)"


# ----------------------------------------------------------------------
# AccessLog Admin
# ----------------------------------------------------------------------
@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ["created_at", "grant_email", "action", "success_badge", "ip_address"]
    list_filter = ["action", "success", "created_at"]
    search_fields = ["grant__email", "ip_address", "error_message"]
    readonly_fields = [f.name for f in AccessLog._meta.fields]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def grant_email(self, obj):
        return obj.grant.email
    grant_email.short_description = "Buyer"

    def success_badge(self, obj):
        if obj.success:
            return format_html('<span style="color:#22c55e;">✓</span>')
        return format_html('<span style="color:#ef4444;">✗</span>')
    success_badge.short_description = "Success"


# ----------------------------------------------------------------------
# DiscountCode Admin
# ----------------------------------------------------------------------
@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = [
        "code", "discount_type", "discount_value_display", "valid_from", "valid_to",
        "used_count", "max_uses", "is_valid_badge", "is_active"
    ]
    list_filter = ["discount_type", "is_active", "valid_from", "valid_to"]
    search_fields = ["code"]
    filter_horizontal = ["assets"]
    actions = ["duplicate_codes"]

    def discount_value_display(self, obj):
        if obj.discount_type == DiscountCode.DiscountType.PERCENT:
            return f"{obj.discount_value}%"
        return f"${obj.discount_value}"
    discount_value_display.short_description = "Discount"

    def is_valid_badge(self, obj):
        if obj.is_valid:
            return format_html('<span style="color:#22c55e;">Valid</span>')
        return format_html('<span style="color:#ef4444;">Invalid</span>')
    is_valid_badge.short_description = "Validity"

    def duplicate_codes(self, request, queryset):
        for code in queryset:
            new_code = code
            new_code.pk = None
            new_code.code = f"{code.code}_copy"
            new_code.used_count = 0
            new_code.save()
            new_code.assets.set(code.assets.all())
        self.message_user(request, f"Duplicated {queryset.count()} discount code(s).")
    duplicate_codes.short_description = "Duplicate selected codes"


# ----------------------------------------------------------------------
# AffiliateClick Admin
# ----------------------------------------------------------------------
@admin.register(AffiliateClick)
class AffiliateClickAdmin(admin.ModelAdmin):
    list_display = ["affiliate_code", "asset_title", "converted", "grant_link", "created_at"]
    list_filter = ["converted", "created_at"]
    search_fields = ["affiliate_code", "ip_address"]
    readonly_fields = [f.name for f in AffiliateClick._meta.fields]
    raw_id_fields = ["asset", "grant"]

    def asset_title(self, obj):
        return obj.asset.title if obj.asset else "—"
    asset_title.short_description = "Asset"

    def grant_link(self, obj):
        if obj.grant:
            url = reverse("admin:gating_accessgrant_change", args=[obj.grant.id])
            return format_html('<a href="{}">{}</a>', url, obj.grant.email)
        return "—"
    grant_link.short_description = "Grant"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# ----------------------------------------------------------------------
# EmbedToken Admin
# ----------------------------------------------------------------------
@admin.register(EmbedToken)
class EmbedTokenAdmin(admin.ModelAdmin):
    list_display = ["token_short", "grant_email", "asset_title", "expires_at", "is_valid_badge", "created_at"]
    list_filter = ["expires_at"]
    search_fields = ["token", "grant__email"]
    readonly_fields = ["token", "created_at"]
    raw_id_fields = ["grant"]

    def token_short(self, obj):
        return obj.token[:16] + "…"
    token_short.short_description = "Token"

    def grant_email(self, obj):
        return obj.grant.email
    grant_email.short_description = "Buyer"

    def asset_title(self, obj):
        return obj.grant.asset.title
    asset_title.short_description = "Asset"

    def is_valid_badge(self, obj):
        if obj.is_valid:
            return format_html('<span style="color:#22c55e;">✓ Valid</span>')
        return format_html('<span style="color:#ef4444;">Expired</span>')
    is_valid_badge.short_description = "Status"

    def has_add_permission(self, request):
        return False