"""
apps/merchants/serializers.py
==============================
Serializers for the merchant layer.

Audiences:
  1. Public (no auth)   — checkout page: see product, submit CustomerCheckout
  2. Merchant (owner)   — manage products, actions, keys, view sales
  3. Admin (staff)      — full read/write on everything
"""

from decimal import Decimal
from django.db.models import Sum
from rest_framework import serializers

from .models import (
    Merchant,
    MerchantAPIKey,
    WebhookDeliveryLog,
    Product,
    CustomerCheckout,
    PostPaymentAction,
)


# ══════════════════════════════════════════════════════════════════════════════
# POST-PAYMENT ACTION
# ══════════════════════════════════════════════════════════════════════════════

class PostPaymentActionSerializer(serializers.ModelSerializer):
    """Full serializer for merchant to manage their automation actions."""

    class Meta:
        model = PostPaymentAction
        fields = [
            "id", "action_type", "priority", "is_active", "config",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_config(self, value):
        action_type = self.initial_data.get("action_type") or (
            self.instance.action_type if self.instance else None
        )
        required_keys = {
            PostPaymentAction.ActionType.TELEGRAM_INVITE: ["invite_link"],
            PostPaymentAction.ActionType.DISCORD_ROLE: ["guild_id", "role_id", "bot_token"],
            PostPaymentAction.ActionType.EMAIL_DELIVERY: ["subject", "body_template"],
            PostPaymentAction.ActionType.WEBHOOK: ["url"],
        }
        missing = [k for k in required_keys.get(action_type, []) if k not in value]
        if missing:
            raise serializers.ValidationError(
                f"Missing required config keys for {action_type}: {missing}"
            )
        return value


class PostPaymentActionPublicSerializer(serializers.ModelSerializer):
    """Safe read-only view for public/buyer context. No secrets exposed."""
    action_type_display = serializers.CharField(
        source="get_action_type_display", read_only=True
    )

    class Meta:
        model = PostPaymentAction
        fields = ["action_type", "action_type_display"]


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCT
# ══════════════════════════════════════════════════════════════════════════════

class ProductPublicSerializer(serializers.ModelSerializer):
    """
    What a buyer sees on the checkout page.
    No sensitive merchant data, no action configs.
    Includes is_test_mode so the checkout page can show the test mode banner.
    """
    merchant_name        = serializers.CharField(source="merchant.business_name", read_only=True)
    merchant_logo        = serializers.CharField(source="merchant.logo_url", read_only=True)
    merchant_description = serializers.CharField(source="merchant.description", read_only=True)
    product_type_display = serializers.CharField(source="get_product_type_display", read_only=True)
    is_sold_out          = serializers.BooleanField(read_only=True)
    purchase_count       = serializers.IntegerField(read_only=True)
    is_test_mode         = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price_usd",
            "min_price_usd",
            "product_type",
            "product_type_display",
            "collect_telegram",
            "collect_discord",
            "collect_phone",
            "collect_custom_field",
            "success_redirect_url",
            "is_sold_out",
            "purchase_count",
            "merchant_name",
            "merchant_logo",
            "merchant_description",
            "is_test_mode",
        ]

    def get_is_test_mode(self, obj) -> bool:
        try:
            return obj.merchant.api_keys.is_test_mode
        except MerchantAPIKey.DoesNotExist:
            return True  # safe default — never accidentally go live


class ProductSerializer(serializers.ModelSerializer):
    """Full serializer for merchant dashboard — create/update their products."""
    post_payment_actions = PostPaymentActionSerializer(many=True, read_only=True)
    purchase_count       = serializers.IntegerField(read_only=True)
    is_sold_out          = serializers.BooleanField(read_only=True)
    revenue_usd          = serializers.SerializerMethodField()
    checkout_url         = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "price_usd",
            "min_price_usd",
            "product_type",
            "collect_telegram",
            "collect_discord",
            "collect_phone",
            "collect_custom_field",
            "success_redirect_url",
            "is_active",
            "max_purchases",
            "purchase_count",
            "is_sold_out",
            "revenue_usd",
            "checkout_url",
            "post_payment_actions",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "slug", "purchase_count", "is_sold_out",
            "revenue_usd", "checkout_url", "created_at", "updated_at",
        ]

    def get_revenue_usd(self, obj) -> str:
        result = obj.customer_checkouts.filter(
            status=CustomerCheckout.Status.COMPLETED,
            is_test=False,  # only count live revenue
        ).aggregate(total=Sum("amount_usd"))
        return str(result["total"] or Decimal("0.00"))

    def get_checkout_url(self, obj) -> str:
        """
        Full public checkout URL for this product.
        Frontend uses this for copy-to-clipboard and QR code generation.
        """
        request = self.context.get("request")
        if request:
            base = f"{request.scheme}://{request.get_host()}"
        else:
            from django.conf import settings
            base = getattr(settings, "FRONTEND_URL", "https://cashspace.com")
        return f"{base}/pay/{obj.merchant.slug}/{obj.slug}/"

    def validate_price_usd(self, value):
        if value is not None and value < Decimal("10"):
            raise serializers.ValidationError("Minimum product price is $10.")
        return value

    def validate(self, attrs):
        product_type = attrs.get("product_type", Product.ProductType.ONE_TIME)
        price = attrs.get("price_usd")
        if product_type != Product.ProductType.DONATION and price is None:
            raise serializers.ValidationError(
                {"price_usd": "Price is required for non-donation products."}
            )
        return attrs


class ProductCreateSerializer(ProductSerializer):
    """Used when merchant creates a new product. Slug is auto-generated."""

    class Meta(ProductSerializer.Meta):
        read_only_fields = [
            "id", "slug", "purchase_count", "is_sold_out",
            "revenue_usd", "checkout_url", "post_payment_actions",
            "created_at", "updated_at",
        ]


# ══════════════════════════════════════════════════════════════════════════════
# MERCHANT API KEYS
# ══════════════════════════════════════════════════════════════════════════════

class MerchantAPIKeySerializer(serializers.ModelSerializer):
    """
    Safe read-only view of a merchant's API keys.

    Secret keys are NEVER returned in full — only the prefix for display
    (e.g. cs_test_sk_aB3xZ9...) and the rotation timestamp.

    The full secret key is only available:
      - Once, immediately after creation (via MerchantRegisterView response)
      - Once, immediately after rotation (via RotateAPIKeyView response)
    """
    active_mode = serializers.CharField(source="active_mode_label", read_only=True)

    class Meta:
        model = MerchantAPIKey
        fields = [
            "is_test_mode",
            "active_mode",
            # Test keys
            "test_publishable_key",
            "test_secret_key_prefix",
            "test_key_rotated_at",
            # Live keys
            "live_publishable_key",
            "live_secret_key_prefix",
            "live_key_rotated_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class MerchantAPIKeyCreatedSerializer(serializers.Serializer):
    """
    Returned ONCE when a merchant is first created or a key is rotated.
    Contains the full raw secret keys — never returned again after this.

    Frontend must display a "Save these keys — you won't see them again"
    warning, same as Stripe.
    """
    test_publishable_key = serializers.CharField()
    test_secret_key      = serializers.CharField(help_text="Save this — shown once only.")
    live_publishable_key = serializers.CharField()
    live_secret_key      = serializers.CharField(help_text="Save this — shown once only.")
    is_test_mode         = serializers.BooleanField()


class ToggleModeSerializer(serializers.Serializer):
    """Request body for switching between test and live mode."""
    mode = serializers.ChoiceField(
        choices=["test", "live"],
        help_text="'test' for sandbox mode, 'live' for real payments.",
    )


class RotateKeySerializer(serializers.Serializer):
    """Request body for rotating a secret key."""
    env = serializers.ChoiceField(
        choices=["test", "live"],
        help_text="Which environment's secret key to rotate.",
    )


class RotateKeyResponseSerializer(serializers.Serializer):
    """
    Returned once after key rotation.
    Contains the new raw secret key — never returned again.
    """
    env            = serializers.CharField()
    new_secret_key = serializers.CharField(help_text="Save this — shown once only.")
    rotated_at     = serializers.DateTimeField()


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK DELIVERY LOG
# ══════════════════════════════════════════════════════════════════════════════

class WebhookDeliveryLogSerializer(serializers.ModelSerializer):
    """
    Merchant-facing view of a webhook delivery attempt.
    Used in the "Webhook logs" tab of the dashboard.
    """
    checkout_email = serializers.CharField(
        source="checkout.email", default=None, read_only=True
    )

    class Meta:
        model = WebhookDeliveryLog
        fields = [
            "id",
            "event_type",
            "endpoint_url",
            "status",
            "attempt_number",
            "response_status_code",
            "response_body",
            "duration_ms",
            "error_message",
            "is_test",
            "next_retry_at",
            "can_retry",
            "checkout_email",
            "created_at",
        ]
        read_only_fields = fields


# ══════════════════════════════════════════════════════════════════════════════
# MERCHANT
# ══════════════════════════════════════════════════════════════════════════════

class MerchantPublicSerializer(serializers.ModelSerializer):
    """Minimal merchant info shown on public checkout pages."""

    class Meta:
        model = Merchant
        fields = [
            "business_name",
            "slug",
            "description",
            "logo_url",
        ]


class MerchantSerializer(serializers.ModelSerializer):
    """
    Merchant's own profile — full read on their own data.
    Includes API key info (safe subset only — no raw secrets).
    Does NOT expose commission_rate_override (admin only).
    """
    products          = ProductSerializer(many=True, read_only=True)
    product_count     = serializers.SerializerMethodField()
    total_sales       = serializers.SerializerMethodField()
    total_revenue_usd = serializers.SerializerMethodField()
    api_keys          = MerchantAPIKeySerializer(read_only=True)
    is_test_mode      = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = [
            "id",
            "business_name",
            "slug",
            "description",
            "logo_url",
            "settlement_blockchain",
            "settlement_currency",
            "settlement_wallet_address",
            "webhook_url",
            "is_active",
            "is_verified",
            "is_test_mode",
            "product_count",
            "total_sales",
            "total_revenue_usd",
            "api_keys",
            "products",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id", "slug", "is_verified", "is_test_mode",
            "product_count", "total_sales", "total_revenue_usd",
            "api_keys", "created_at", "updated_at",
        ]

    def get_is_test_mode(self, obj) -> bool:
        try:
            return obj.api_keys.is_test_mode
        except MerchantAPIKey.DoesNotExist:
            return True

    def get_product_count(self, obj) -> int:
        return obj.products.filter(is_active=True).count()

    def get_total_sales(self, obj) -> int:
        return CustomerCheckout.objects.filter(
            product__merchant=obj,
            status=CustomerCheckout.Status.COMPLETED,
            is_test=False,  # only live sales count
        ).count()

    def get_total_revenue_usd(self, obj) -> str:
        result = CustomerCheckout.objects.filter(
            product__merchant=obj,
            status=CustomerCheckout.Status.COMPLETED,
            is_test=False,
        ).aggregate(total=Sum("amount_usd"))
        return str(result["total"] or Decimal("0.00"))


class MerchantCreateSerializer(serializers.ModelSerializer):
    """
    Used when a user registers as a merchant for the first time.
    User is injected from request in the view.
    Response includes raw API keys — shown once only.
    """

    class Meta:
        model = Merchant
        fields = [
            "business_name",
            "description",
            "logo_url",
            "settlement_blockchain",
            "settlement_currency",
            "settlement_wallet_address",
            "webhook_url",
            "webhook_secret",
        ]

    def validate(self, attrs):
        user = self.context["request"].user
        if Merchant.objects.filter(user=user).exists():
            raise serializers.ValidationError(
                "You already have a merchant account."
            )
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        return Merchant.objects.create(user=user, **validated_data)


class MerchantUpdateSerializer(serializers.ModelSerializer):
    """Partial updates to merchant profile. Slug is immutable after creation."""

    class Meta:
        model = Merchant
        fields = [
            "business_name",
            "description",
            "logo_url",
            "settlement_blockchain",
            "settlement_currency",
            "settlement_wallet_address",
            "webhook_url",
            "webhook_secret",
            "is_active",
        ]


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMER CHECKOUT
# ══════════════════════════════════════════════════════════════════════════════

class CustomerCheckoutSerializer(serializers.ModelSerializer):
    """
    Submitted by the buyer at /pay/<merchant>/<product>/.
    Dynamic validation: required fields depend on product configuration.
    """

    class Meta:
        model = CustomerCheckout
        fields = [
            "id",
            "email",
            "full_name",
            "telegram_username",
            "discord_username",
            "phone_number",
            "custom_field_value",
            "amount_usd",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        product: Product = self.context.get("product")
        if not product:
            raise serializers.ValidationError("Product context is missing.")

        if product.collect_telegram and not attrs.get("telegram_username"):
            raise serializers.ValidationError(
                {"telegram_username": "Your Telegram username is required for this product."}
            )
        if product.collect_discord and not attrs.get("discord_username"):
            raise serializers.ValidationError(
                {"discord_username": "Your Discord username is required for this product."}
            )
        if product.collect_phone and not attrs.get("phone_number"):
            raise serializers.ValidationError(
                {"phone_number": "Your phone number is required for this product."}
            )
        if product.collect_custom_field and not attrs.get("custom_field_value"):
            raise serializers.ValidationError(
                {"custom_field_value": f"{product.collect_custom_field} is required."}
            )

        amount = attrs.get("amount_usd")
        if amount is None:
            if product.product_type != Product.ProductType.DONATION:
                attrs["amount_usd"] = product.price_usd
            else:
                raise serializers.ValidationError(
                    {"amount_usd": "Please enter the amount you want to pay."}
                )

        final_amount = attrs["amount_usd"]
        min_price = product.min_price_usd or Decimal("10")
        if final_amount < min_price:
            raise serializers.ValidationError(
                {"amount_usd": f"Minimum payment is ${min_price}."}
            )

        if product.is_sold_out:
            raise serializers.ValidationError(
                "This product is sold out and no longer accepting payments."
            )

        return attrs

    def create(self, validated_data):
        product = self.context["product"]
        request = self.context.get("request")
        is_test = self.context.get("is_test", False)
        return CustomerCheckout.objects.create(
            product=product,
            is_test=is_test,
            ip_address=self._get_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", "") if request else "",
            **validated_data,
        )

    def _get_ip(self, request):
        if not request:
            return None
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")


class CustomerCheckoutDetailSerializer(serializers.ModelSerializer):
    """
    Merchant's view of a single buyer checkout + payment status.
    Used in the Sales CRM tab.
    """
    payment_status = serializers.CharField(source="payment.status", default="—")
    payout_status  = serializers.CharField(source="payment.payout_status", default="—")
    payment_id     = serializers.UUIDField(source="payment.id", default=None)
    product_name   = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = CustomerCheckout
        fields = [
            "id",
            "product_name",
            "email",
            "full_name",
            "telegram_username",
            "discord_username",
            "phone_number",
            "custom_field_value",
            "amount_usd",
            "is_test",
            "status",
            "automation_triggered",
            "automation_triggered_at",
            "automation_error",
            "payment_id",
            "payment_status",
            "payout_status",
            "created_at",
        ]
        read_only_fields = fields


# ══════════════════════════════════════════════════════════════════════════════
# ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

class MerchantAnalyticsSerializer(serializers.Serializer):
    """
    Response shape for GET /merchants/me/analytics/
    Covers revenue, sales volume, conversion rate, top products.
    """
    period              = serializers.CharField()
    total_revenue_usd   = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_sales         = serializers.IntegerField()
    total_checkouts     = serializers.IntegerField()
    conversion_rate_pct = serializers.FloatField()
    daily_revenue       = serializers.ListField(child=serializers.DictField())
    top_products        = serializers.ListField(child=serializers.DictField())


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════════════════════

class AdminMerchantSerializer(serializers.ModelSerializer):
    """Full merchant view for staff — includes commission override and verified flag."""
    user_email  = serializers.CharField(source="user.email", read_only=True)
    total_sales = serializers.SerializerMethodField()
    is_test_mode = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_total_sales(self, obj) -> int:
        return CustomerCheckout.objects.filter(
            product__merchant=obj,
            status=CustomerCheckout.Status.COMPLETED,
        ).count()

    def get_is_test_mode(self, obj) -> bool:
        try:
            return obj.api_keys.is_test_mode
        except MerchantAPIKey.DoesNotExist:
            return True