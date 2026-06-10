"""
apps/creator/serializers.py
===========================
Advanced serializers for the creator app.

Provides:
  - Creator profile (read/write)
  - Payable asset CRUD with nested fields
  - Sale listing and detail
  - Affiliate program management
  - Discount code management
  - Public asset serializer for checkout pages
  - Checkout request/response serializers
"""

from decimal import Decimal
from rest_framework import serializers
from django.core.validators import URLValidator, MinValueValidator
from django.utils import timezone

from .models import (
    CreatorProfile, PayableAsset, CreatorSale,
    CreatorAffiliateProgram, CreatorDiscountCode
)


# ----------------------------------------------------------------------
# Creator Profile Serializer
# ----------------------------------------------------------------------
class CreatorProfileSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    effective_commission_rate = serializers.DecimalField(max_digits=5, decimal_places=4, read_only=True)
    total_earnings_usd = serializers.SerializerMethodField()

    class Meta:
        model = CreatorProfile
        fields = [
            "id", "user_id", "user_email", "display_name", "bio",
            "avatar_url", "cover_image_url", "website", "twitter_handle",
            "telegram_handle", "custom_payout_wallet", "custom_payout_blockchain",
            "custom_payout_currency", "commission_rate_override", "effective_commission_rate",
            "is_verified", "max_assets", "max_monthly_sales",
            "total_views", "total_sales", "total_revenue_usd", "total_earnings_usd",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "user_id", "user_email", "effective_commission_rate", "is_verified",
            "total_views", "total_sales", "total_revenue_usd", "total_earnings_usd",
            "created_at", "updated_at",
        ]

    def get_total_earnings_usd(self, obj):
        """Net earnings after commission (sum of net_usd from all sales)."""
        from django.db.models import Sum
        total = obj.assets.aggregate(net=Sum("sales__net_usd"))["net"]
        return str(total or Decimal("0.00"))

    def validate_commission_rate_override(self, value):
        if value is not None and (value < 0 or value > 1):
            raise serializers.ValidationError("Commission rate must be between 0 and 1.")
        return value


# ----------------------------------------------------------------------
# Payable Asset Serializers
# ----------------------------------------------------------------------
class PayableAssetListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for asset listing (dashboard table)."""
    creator_name = serializers.CharField(source="creator.display_name", read_only=True)
    total_sales_count = serializers.IntegerField(read_only=True)
    net_revenue_usd = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = PayableAsset
        fields = [
            "id", "title", "slug", "asset_type", "pricing_type",
            "price_usd", "is_active", "total_sales_count",
            "net_revenue_usd", "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at", "total_sales_count", "net_revenue_usd"]


class PayableAssetDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer for asset management (create/update/view)."""
    creator = CreatorProfileSerializer(read_only=True)
    total_sales_count = serializers.IntegerField(read_only=True)
    net_revenue_usd = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_sold_out = serializers.BooleanField(read_only=True)
    checkout_url = serializers.SerializerMethodField()
    shareable_link = serializers.SerializerMethodField()

    class Meta:
        model = PayableAsset
        fields = [
            "id", "creator", "title", "slug", "description", "thumbnail_url",
            "video_preview_url", "asset_type", "unlock_value", "unlock_config",
            "pricing_type", "price_usd", "min_price_usd", "max_price_usd",
            "price_tiers", "subscription_interval_days", "subscription_trial_days",
            "subscription_max_cycles", "access_duration_value", "access_duration_unit",
            "is_active", "max_sales", "max_sales_per_buyer", "allowed_countries",
            "require_captcha", "custom_settlement_wallet", "custom_settlement_blockchain",
            "custom_settlement_currency", "token_expires_hours", "token_max_uses",
            "success_message", "success_redirect_url", "send_welcome_email",
            "custom_email_template", "webhook_url", "webhook_secret",
            "view_count", "conversion_count", "revenue_usd", "total_sales_count",
            "net_revenue_usd", "is_sold_out", "checkout_url", "shareable_link",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "slug", "creator", "view_count", "conversion_count",
            "revenue_usd", "total_sales_count", "net_revenue_usd",
            "is_sold_out", "created_at", "updated_at",
        ]

    def get_checkout_url(self, obj):
        request = self.context.get("request")
        if request:
            return f"{request.scheme}://{request.get_host()}/creator/pay/{obj.slug}/"
        return f"/creator/pay/{obj.slug}/"

    def get_shareable_link(self, obj):
        request = self.context.get("request")
        if request:
            return f"{request.scheme}://{request.get_host()}/creator/{obj.slug}"
        return f"/creator/{obj.slug}"

    def validate_unlock_value(self, value):
        asset_type = self.initial_data.get("asset_type") or getattr(self.instance, "asset_type", None)
        if asset_type in ["url", "telegram", "webhook"]:
            URLValidator()(value)
        return value

    def validate_price_usd(self, value):
        if value is not None and value < Decimal("0.01"):
            raise serializers.ValidationError("Price must be at least $0.01")
        return value

    def validate_price_tiers(self, value):
        if value:
            for tier in value:
                if "price" not in tier or "duration_days" not in tier:
                    raise serializers.ValidationError("Each tier must have 'price' and 'duration_days'")
                if tier["price"] < Decimal("0.01"):
                    raise serializers.ValidationError("Tier price must be at least $0.01")
        return value

    def validate(self, attrs):
        pricing_type = attrs.get("pricing_type", getattr(self.instance, "pricing_type", None))
        if pricing_type == PayableAsset.PricingType.FIXED:
            if not attrs.get("price_usd") and (not self.instance or not self.instance.price_usd):
                raise serializers.ValidationError({"price_usd": "Required for fixed pricing."})
        if pricing_type == PayableAsset.PricingType.TIERED:
            if not attrs.get("price_tiers") and (not self.instance or not self.instance.price_tiers):
                raise serializers.ValidationError({"price_tiers": "At least one tier required."})
        return attrs

    def create(self, validated_data):
        request = self.context.get("request")
        creator = request.user.creator_profile if request else validated_data.get("creator")
        asset = PayableAsset.objects.create(creator=creator, **validated_data)
        return asset


class PayableAssetCreateSerializer(PayableAssetDetailSerializer):
    """Create serializer – creator is injected from view."""
    class Meta(PayableAssetDetailSerializer.Meta):
        read_only_fields = [
            "id", "slug", "creator", "view_count", "conversion_count",
            "revenue_usd", "total_sales_count", "net_revenue_usd",
            "is_sold_out", "created_at", "updated_at",
        ]


class PublicAssetSerializer(serializers.ModelSerializer):
    """Serializer for public checkout page (no sensitive data)."""
    creator_name = serializers.CharField(source="creator.display_name", read_only=True)
    creator_avatar = serializers.URLField(source="creator.avatar_url", read_only=True)
    formatted_price = serializers.SerializerMethodField()
    is_sold_out = serializers.BooleanField(read_only=True)

    class Meta:
        model = PayableAsset
        fields = [
            "id", "slug", "title", "description", "thumbnail_url",
            "video_preview_url", "asset_type", "pricing_type", "price_usd",
            "min_price_usd", "max_price_usd", "price_tiers", "formatted_price",
            "is_sold_out", "creator_name", "creator_avatar",
        ]

    def get_formatted_price(self, obj):
        if obj.pricing_type == PayableAsset.PricingType.FIXED:
            return f"${obj.price_usd}"
        if obj.pricing_type == PayableAsset.PricingType.PAY_WHAT_YOU_WANT:
            return f"From ${obj.min_price_usd}"
        if obj.pricing_type == PayableAsset.PricingType.TIERED:
            return "Choose tier"
        return "Subscription"


# ----------------------------------------------------------------------
# Creator Sale Serializers
# ----------------------------------------------------------------------
class CreatorSaleSerializer(serializers.ModelSerializer):
    asset_title = serializers.CharField(source="asset.title", read_only=True)
    asset_slug = serializers.CharField(source="asset.slug", read_only=True)

    class Meta:
        model = CreatorSale
        fields = [
            "id", "asset", "asset_title", "asset_slug", "buyer_email",
            "buyer_name", "amount_usd", "commission_usd", "net_usd",
            "status", "paid_at", "created_at",
        ]
        read_only_fields = fields


class CreatorSaleDetailSerializer(serializers.ModelSerializer):
    asset = PayableAssetListSerializer(read_only=True)
    access_token_display = serializers.SerializerMethodField()

    class Meta:
        model = CreatorSale
        fields = [
            "id", "asset", "buyer_email", "buyer_name", "amount_usd",
            "commission_usd", "net_usd", "status", "access_token",
            "access_token_display", "payment_id", "payout_id",
            "paid_at", "metadata", "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_access_token_display(self, obj):
        token = obj.access_token
        if token and len(token) > 16:
            return f"{token[:8]}...{token[-8:]}"
        return token


# ----------------------------------------------------------------------
# Affiliate Program Serializer
# ----------------------------------------------------------------------
class CreatorAffiliateProgramSerializer(serializers.ModelSerializer):
    asset_title = serializers.CharField(source="asset.title", read_only=True)
    total_affiliate_sales = serializers.SerializerMethodField()
    total_affiliate_earnings = serializers.SerializerMethodField()

    class Meta:
        model = CreatorAffiliateProgram
        fields = [
            "id", "asset", "asset_title", "commission_percent",
            "is_active", "cookie_days", "total_affiliate_sales",
            "total_affiliate_earnings",
        ]
        read_only_fields = ["id", "total_affiliate_sales", "total_affiliate_earnings"]

    def get_total_affiliate_sales(self, obj):
        # Assumes sales metadata contains affiliate_code
        from django.db.models import Count
        return obj.asset.sales.filter(metadata__has_key="affiliate_code").count()

    def get_total_affiliate_earnings(self, obj):
        from django.db.models import Sum
        total = obj.asset.sales.filter(metadata__has_key="affiliate_code").aggregate(
            total=Sum("net_usd")
        )["total"]
        return str(total or Decimal("0.00"))


# ----------------------------------------------------------------------
# Discount Code Serializer
# ----------------------------------------------------------------------
class CreatorDiscountCodeSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    asset_title = serializers.CharField(source="asset.title", read_only=True)

    class Meta:
        model = CreatorDiscountCode
        fields = [
            "id", "asset", "asset_title", "code", "discount_type",
            "discount_value", "max_uses", "used_count", "valid_from",
            "valid_to", "is_active", "is_valid",
        ]
        read_only_fields = ["id", "used_count", "is_valid"]

    def validate_code(self, value):
        value = value.upper().strip()
        if CreatorDiscountCode.objects.filter(asset=self.context.get("asset"), code=value).exists():
            raise serializers.ValidationError("Discount code already exists for this asset.")
        return value

    def validate_discount_value(self, value):
        if value <= 0:
            raise serializers.ValidationError("Discount value must be positive.")
        if self.initial_data.get("discount_type") == "percent" and value > 100:
            raise serializers.ValidationError("Percentage discount cannot exceed 100%.")
        return value

    def validate(self, attrs):
        if attrs.get("valid_to") and attrs.get("valid_from") and attrs["valid_to"] <= attrs["valid_from"]:
            raise serializers.ValidationError({"valid_to": "Must be after valid_from."})
        return attrs


# ----------------------------------------------------------------------
# Public Checkout Serializers
# ----------------------------------------------------------------------
class PublicCheckoutRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    amount_usd = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    tier_index = serializers.IntegerField(min_value=0, required=False)
    discount_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    affiliate_code = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate(self, attrs):
        asset = self.context.get("asset")
        if not asset:
            raise serializers.ValidationError("Asset context missing.")
        if asset.pricing_type == PayableAsset.PricingType.PAY_WHAT_YOU_WANT:
            amount = attrs.get("amount_usd")
            if not amount:
                raise serializers.ValidationError({"amount_usd": "Required for pay-what-you-want."})
            if amount < asset.min_price_usd:
                raise serializers.ValidationError({"amount_usd": f"Minimum ${asset.min_price_usd}."})
            if asset.max_price_usd and amount > asset.max_price_usd:
                raise serializers.ValidationError({"amount_usd": f"Maximum ${asset.max_price_usd}."})
        if asset.pricing_type == PayableAsset.PricingType.TIERED:
            tier_idx = attrs.get("tier_index")
            if tier_idx is None:
                raise serializers.ValidationError({"tier_index": "Select a pricing tier."})
            if tier_idx >= len(asset.price_tiers):
                raise serializers.ValidationError({"tier_index": "Invalid tier."})
        return attrs


class PublicCheckoutResponseSerializer(serializers.Serializer):
    sale_id = serializers.UUIDField()
    payment_url = serializers.URLField()
    amount_usd = serializers.DecimalField(max_digits=12, decimal_places=2)
    asset_title = serializers.CharField()
    expires_at = serializers.DateTimeField(required=False)


# ----------------------------------------------------------------------
# Analytics & Stats Serializer
# ----------------------------------------------------------------------
class CreatorStatsSerializer(serializers.Serializer):
    period = serializers.ChoiceField(choices=["day", "week", "month", "year", "all"], default="month")
    total_sales = serializers.IntegerField(read_only=True)
    total_revenue_usd = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    total_net_usd = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    average_order_value = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    conversion_rate = serializers.FloatField(read_only=True)
    sales_by_day = serializers.JSONField(read_only=True)
    top_assets = serializers.JSONField(read_only=True)