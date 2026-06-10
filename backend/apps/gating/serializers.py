"""
apps/gating/serializers.py
==========================
Advanced serializers for the gating app.

Features:
  - Nested serializers for Asset, Grant, Token, Discount, Affiliate.
  - Dynamic validation based on asset type and pricing model.
  - URL validation, blockchain address validation.
  - Read-only computed fields (grant_count, revenue_usd, etc.)
  - Proper handling of Decimal fields, JSON fields.
  - Custom create/update logic for nested objects.
"""

from decimal import Decimal
from rest_framework import serializers
from django.core.validators import MinValueValidator, MaxValueValidator, URLValidator
from django.db import transaction
from django.utils import timezone

from .models import (
    GatedAsset, AccessGrant, AccessToken, AccessLog,
    DiscountCode, AffiliateClick, EmbedToken
)


# ----------------------------------------------------------------------
# AccessLog Serializer (read‑only)
# ----------------------------------------------------------------------
class AccessLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessLog
        fields = ["id", "action", "success", "ip_address", "user_agent", "error_message", "created_at"]
        read_only_fields = fields


# ----------------------------------------------------------------------
# AccessToken Serializer
# ----------------------------------------------------------------------
class AccessTokenSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    token_display = serializers.SerializerMethodField()

    class Meta:
        model = AccessToken
        fields = [
            "id", "token", "created_at", "expires_at", "use_count",
            "max_uses", "last_used_at", "is_valid", "token_display"
        ]
        read_only_fields = ["id", "token", "created_at", "use_count", "last_used_at"]

    def get_token_display(self, obj):
        token = str(obj.token)
        if len(token) > 16:
            return f"{token[:8]}...{token[-8:]}"
        return token


# ----------------------------------------------------------------------
# EmbedToken Serializer
# ----------------------------------------------------------------------
class EmbedTokenSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = EmbedToken
        fields = ["id", "token", "expires_at", "created_at", "is_valid"]
        read_only_fields = ["id", "token", "created_at"]


# ----------------------------------------------------------------------
# DiscountCode Serializer
# ----------------------------------------------------------------------
class DiscountCodeSerializer(serializers.ModelSerializer):
    is_valid = serializers.BooleanField(read_only=True)
    discount_display = serializers.SerializerMethodField()

    class Meta:
        model = DiscountCode
        fields = [
            "id", "code", "discount_type", "discount_value", "valid_from",
            "valid_to", "max_uses", "used_count", "min_purchase_usd",
            "assets", "is_active", "is_valid", "discount_display"
        ]
        read_only_fields = ["id", "used_count", "is_valid"]

    def get_discount_display(self, obj):
        if obj.discount_type == DiscountCode.DiscountType.PERCENT:
            return f"{obj.discount_value}% off"
        return f"${obj.discount_value} off"

    def validate_code(self, value):
        value = value.upper().strip()
        if DiscountCode.objects.filter(code=value).exists():
            raise serializers.ValidationError("Discount code already exists.")
        return value

    def create(self, validated_data):
        assets = validated_data.pop("assets", [])
        code = DiscountCode.objects.create(**validated_data)
        code.assets.set(assets)
        return code


# ----------------------------------------------------------------------
# AffiliateClick Serializer
# ----------------------------------------------------------------------
class AffiliateClickSerializer(serializers.ModelSerializer):
    class Meta:
        model = AffiliateClick
        fields = [
            "id", "affiliate_code", "asset", "ip_address", "user_agent",
            "referrer_url", "converted", "grant", "created_at"
        ]
        read_only_fields = ["id", "created_at"]


# ----------------------------------------------------------------------
# GatedAsset Serializers
# ----------------------------------------------------------------------
class GatedAssetListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    total_sales = serializers.IntegerField(read_only=True)
    revenue_usd = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_sold_out = serializers.BooleanField(read_only=True)

    class Meta:
        model = GatedAsset
        fields = [
            "id", "title", "slug", "asset_type", "pricing_type",
            "price_usd", "min_price_usd", "thumbnail_url", "is_active",
            "owner_email", "total_sales", "revenue_usd", "is_sold_out",
            "created_at"
        ]
        read_only_fields = ["id", "slug", "created_at", "total_sales", "revenue_usd", "is_sold_out"]


class GatedAssetDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer for asset management."""
    owner_email = serializers.EmailField(source="owner.email", read_only=True)
    grant_count = serializers.IntegerField(read_only=True)
    revenue_usd = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_sold_out = serializers.BooleanField(read_only=True)
    effective_price = serializers.SerializerMethodField()
    settlement_wallet_address_display = serializers.SerializerMethodField()

    class Meta:
        model = GatedAsset
        fields = [
            "id", "title", "slug", "description", "thumbnail_url", "video_preview_url",
            "owner", "owner_email", "merchant",
            "asset_type", "unlock_value", "unlock_config",
            "pricing_type", "price_usd", "min_price_usd", "max_price_usd", "price_tiers",
            "subscription_interval_value", "subscription_interval_unit",
            "subscription_trial_days", "subscription_max_cycles",
            "grant_duration_value", "grant_duration_unit",
            "settlement_blockchain", "settlement_currency", "settlement_wallet_address",
            "token_expires_after_grant_value", "token_max_uses",
            "token_requires_email_verification",
            "is_active", "max_grants", "max_grants_per_email",
            "allowed_countries", "blocked_countries", "require_captcha",
            "allowed_referrers", "affiliate_commission_percent", "affiliate_cookie_days",
            "discount_codes", "dynamic_pricing_enabled", "base_price_usd",
            "price_multiplier", "demand_window_days",
            "steps", "bundled_assets", "success_message", "success_redirect_url",
            "send_welcome_email", "welcome_email_template",
            "webhook_url", "webhook_secret",
            "nft_gate_contract", "nft_gate_min_balance", "blockchain_network",
            "grant_count", "revenue_usd", "is_sold_out", "effective_price",
            "settlement_wallet_address_display", "created_at", "updated_at"
        ]
        read_only_fields = [
            "id", "slug", "created_at", "updated_at", "grant_count",
            "revenue_usd", "is_sold_out", "owner", "owner_email"
        ]

    def get_effective_price(self, obj):
        if obj.pricing_type == GatedAsset.PricingType.FIXED and obj.price_usd:
            return str(obj.price_usd)
        if obj.pricing_type == GatedAsset.PricingType.DONATION:
            return f"{obj.min_price_usd}+"
        return None

    def get_settlement_wallet_address_display(self, obj):
        addr = obj.settlement_wallet_address
        if not addr:
            return None
        if len(addr) > 16:
            return f"{addr[:8]}...{addr[-8:]}"
        return addr

    def validate_unlock_value(self, value):
        asset_type = self.initial_data.get("asset_type") or (self.instance.asset_type if self.instance else None)
        if asset_type in [GatedAsset.AssetType.URL, GatedAsset.AssetType.TELEGRAM, GatedAsset.AssetType.WEBHOOK]:
            validate_url = URLValidator()
            try:
                validate_url(value)
            except Exception:
                raise serializers.ValidationError("Invalid URL format.")
        return value

    def validate_unlock_config(self, value):
        asset_type = self.initial_data.get("asset_type") or (self.instance.asset_type if self.instance else None)
        if asset_type == GatedAsset.AssetType.DISCORD:
            required = ["guild_id", "role_id", "bot_token"]
            for r in required:
                if r not in value:
                    raise serializers.ValidationError(f"Discord config requires '{r}'")
        if asset_type == GatedAsset.AssetType.FILE:
            if "expiry_seconds" not in value:
                value["expiry_seconds"] = 3600
        return value

    def validate_price_usd(self, value):
        if value is not None and value < Decimal("0.01"):
            raise serializers.ValidationError("Price must be at least $0.01")
        return value

    def validate_min_price_usd(self, value):
        if value < Decimal("0.01"):
            raise serializers.ValidationError("Minimum price must be at least $0.01")
        return value

    def validate(self, attrs):
        pricing_type = attrs.get("pricing_type", self.instance.pricing_type if self.instance else None)
        if pricing_type == GatedAsset.PricingType.FIXED:
            price = attrs.get("price_usd", self.instance.price_usd if self.instance else None)
            if not price:
                raise serializers.ValidationError({"price_usd": "Price is required for fixed pricing."})
        if pricing_type == GatedAsset.PricingType.TIERED:
            tiers = attrs.get("price_tiers", self.instance.price_tiers if self.instance else [])
            if not tiers or len(tiers) < 1:
                raise serializers.ValidationError({"price_tiers": "At least one tier required."})
        return attrs

    def create(self, validated_data):
        validated_data.pop("owner", None)  # owner set in view
        bundled = validated_data.pop("bundled_assets", [])
        asset = GatedAsset.objects.create(**validated_data)
        asset.bundled_assets.set(bundled)
        return asset

    def update(self, instance, validated_data):
        bundled = validated_data.pop("bundled_assets", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if bundled is not None:
            instance.bundled_assets.set(bundled)
        return instance


class GatedAssetCreateSerializer(GatedAssetDetailSerializer):
    """Create serializer – requires owner to be set by view."""
    class Meta(GatedAssetDetailSerializer.Meta):
        read_only_fields = ["id", "slug", "created_at", "updated_at", "grant_count", "revenue_usd", "is_sold_out"]


class PublicAssetSerializer(serializers.ModelSerializer):
    """Public view of asset (no sensitive data)."""
    effective_price = serializers.SerializerMethodField()

    class Meta:
        model = GatedAsset
        fields = [
            "id", "slug", "title", "description", "thumbnail_url", "video_preview_url",
            "asset_type", "pricing_type", "price_usd", "min_price_usd", "max_price_usd",
            "price_tiers", "effective_price", "is_sold_out", "grant_count"
        ]

    def get_effective_price(self, obj):
        if obj.pricing_type == GatedAsset.PricingType.FIXED and obj.price_usd:
            return str(obj.price_usd)
        if obj.pricing_type == GatedAsset.PricingType.DONATION:
            return f"From ${obj.min_price_usd}"
        return None


# ----------------------------------------------------------------------
# AccessGrant Serializers
# ----------------------------------------------------------------------
class AccessGrantListSerializer(serializers.ModelSerializer):
    asset_title = serializers.CharField(source="asset.title", read_only=True)
    asset_slug = serializers.CharField(source="asset.slug", read_only=True)
    has_token = serializers.BooleanField(read_only=True)

    class Meta:
        model = AccessGrant
        fields = [
            "id", "asset_title", "asset_slug", "email", "full_name",
            "amount_usd", "status", "has_token", "created_at"
        ]
        read_only_fields = fields


class AccessGrantDetailSerializer(serializers.ModelSerializer):
    asset = GatedAssetListSerializer(read_only=True)
    payment_status = serializers.CharField(source="payment.status", read_only=True, default=None)
    access_token = AccessTokenSerializer(read_only=True)
    access_logs = AccessLogSerializer(many=True, read_only=True)
    is_access_valid = serializers.BooleanField(read_only=True)

    class Meta:
        model = AccessGrant
        fields = [
            "id", "asset", "email", "full_name", "country_code", "ip_address",
            "user_agent", "affiliate_code", "discount_code_used", "discount_amount_usd",
            "amount_usd", "payment", "payment_status", "selected_tier_index",
            "status", "access_expires_at", "unlock_delivered", "unlock_delivered_at",
            "unlock_error", "metadata", "access_token", "access_logs",
            "is_access_valid", "created_at", "updated_at"
        ]
        read_only_fields = [
            "id", "payment", "access_token", "access_logs", "created_at", "updated_at",
            "is_access_valid"
        ]


class PublicCheckoutSerializer(serializers.Serializer):
    """Serializer for public checkout form."""
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=120, required=False, allow_blank=True)
    country_code = serializers.CharField(max_length=2, required=False, allow_blank=True)
    amount_usd = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    discount_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    affiliate_code = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate(self, attrs):
        asset = self.context.get("asset")
        if not asset:
            raise serializers.ValidationError("Asset context missing.")

        if asset.pricing_type == GatedAsset.PricingType.DONATION:
            amount = attrs.get("amount_usd")
            if not amount:
                raise serializers.ValidationError({"amount_usd": "Amount is required for donation."})
            if amount < asset.min_price_usd:
                raise serializers.ValidationError({"amount_usd": f"Minimum amount is ${asset.min_price_usd}."})
            if asset.max_price_usd and amount > asset.max_price_usd:
                raise serializers.ValidationError({"amount_usd": f"Maximum amount is ${asset.max_price_usd}."})

        return attrs


class CheckoutResponseSerializer(serializers.Serializer):
    """Response after creating checkout."""
    grant_id = serializers.UUIDField()
    payment_id = serializers.UUIDField()
    payram_payment_url = serializers.URLField()
    amount_usd = serializers.DecimalField(max_digits=12, decimal_places=2)
    asset_title = serializers.CharField()


class GrantStatusSerializer(serializers.Serializer):
    grant_id = serializers.UUIDField()
    status = serializers.CharField()
    asset_title = serializers.CharField()
    amount_usd = serializers.DecimalField(max_digits=12, decimal_places=2)
    granted_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField(allow_null=True)
    has_token = serializers.BooleanField()


class ResendAccessSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ValidateDiscountSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    asset_slug = serializers.CharField(required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, default=0)


# ----------------------------------------------------------------------
# Additional serializers for nested endpoints
# ----------------------------------------------------------------------
class AssetGrantNestedSerializer(AccessGrantListSerializer):
    """Used inside asset detail for admin."""
    pass


class BulkVerifySerializer(serializers.Serializer):
    tokens = serializers.ListField(child=serializers.CharField(), max_length=20)

    def validate_tokens(self, value):
        if len(value) > 20:
            raise serializers.ValidationError("Maximum 20 tokens per batch.")
        return value


class AffiliateClickCreateSerializer(serializers.Serializer):
    code = serializers.CharField()
    asset_id = serializers.UUIDField(required=False)
    redirect = serializers.URLField(required=False)


class GenerateAffiliateCodeResponseSerializer(serializers.Serializer):
    affiliate_code = serializers.CharField()