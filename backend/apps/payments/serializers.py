# apps/payments/serializers.py
# Enterprise-grade serializers supporting multi-chain / multi-currency payments

from decimal import Decimal
from rest_framework import serializers

from apps.accounts.models import User
from .models import Payment, UserCryptoWallet, WebhookEvent, VALID_PAYRAM_PAIRS


# ── Initiate Payment Serializer (with wallet selection) ───────────────────────

class InitiatePaymentSerializer(serializers.Serializer):
    """
    Validate payment initiation request.
    User must select an active crypto wallet (blockchain + currency + address).
    """
    amount_usd = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("10"),
        max_value=Decimal("10000"),
        help_text="Amount in USD (min $10, max $10,000)",
    )
    wallet_id = serializers.UUIDField(
        help_text="UUID of the UserCryptoWallet to receive the payout"
    )

    def validate_wallet_id(self, value):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError("Authentication required.")

        try:
            wallet = UserCryptoWallet.objects.get(
                id=value, user=request.user, is_active=True
            )
        except UserCryptoWallet.DoesNotExist:
            raise serializers.ValidationError(
                "Invalid or inactive wallet. Please select an active wallet."
            )

        # Validate that the blockchain/currency pair is supported by PayRam
        valid_currencies = VALID_PAYRAM_PAIRS.get(wallet.blockchain_code, [])
        if wallet.currency_code not in valid_currencies:
            raise serializers.ValidationError(
                f"Unsupported pair: {wallet.blockchain_code}/{wallet.currency_code}. "
                f"Please add a different wallet."
            )

        return value


# ── User‑facing Payment Serializers (multi‑chain) ─────────────────────────────

class PaymentSerializer(serializers.ModelSerializer):
    """Basic payment list view – no sensitive internal fields."""
    blockchain_display = serializers.CharField(source="get_blockchain_code_display", read_only=True)
    currency_display = serializers.CharField(source="get_currency_code_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "amount_usd",
            "commission_usd",
            "payout_usd_equivalent",
            "payout_crypto_amount",
            "commission_rate",
            "blockchain_code",
            "blockchain_display",
            "currency_code",
            "currency_display",
            "destination_wallet",
            "status",
            "payout_status",
            "payram_reference_id",
            "payram_payment_url",
            "payram_payout_id",
            "payout_initiated_at",
            "payout_completed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PaymentDetailSerializer(serializers.ModelSerializer):
    """Full detail for a single payment (including raw state and error info)."""
    blockchain_display = serializers.CharField(source="get_blockchain_code_display", read_only=True)
    currency_display = serializers.CharField(source="get_currency_code_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "amount_usd",
            "commission_usd",
            "payout_usd_equivalent",
            "payout_crypto_amount",
            "exchange_rate_usd_to_crypto",
            "commission_rate",
            "blockchain_code",
            "blockchain_display",
            "currency_code",
            "currency_display",
            "destination_wallet",
            "status",
            "payout_status",
            "payram_reference_id",
            "payram_payment_url",
            "payram_raw_status",
            "payram_payout_id",
            "payout_initiated_at",
            "payout_completed_at",
            "payout_error",
            "error_message",
            "payment_method",
            "payment_method_details",
            "last_webhook_at",
            "webhook_count",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


# ── Admin Payment Serializer (includes user relation) ─────────────────────────

class AdminPaymentSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_id = serializers.CharField(source="user.id", read_only=True)
    blockchain_display = serializers.CharField(source="get_blockchain_code_display", read_only=True)
    currency_display = serializers.CharField(source="get_currency_code_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "user_id",
            "user_email",
            "amount_usd",
            "commission_usd",
            "payout_usd_equivalent",
            "payout_crypto_amount",
            "exchange_rate_usd_to_crypto",
            "commission_rate",
            "blockchain_code",
            "blockchain_display",
            "currency_code",
            "currency_display",
            "destination_wallet",
            "status",
            "payout_status",
            "payram_reference_id",
            "payram_payment_url",
            "payram_raw_status",
            "payram_payout_id",
            "payout_initiated_at",
            "payout_completed_at",
            "payout_error",
            "error_message",
            "payment_method",
            "payment_method_details",
            "last_webhook_at",
            "webhook_count",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


# ── Webhook Event Serializer ─────────────────────────────────────────────────

class WebhookEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = WebhookEvent
        fields = [
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
        read_only_fields = fields


# ── Crypto Wallet Serializers (for multi‑currency wallets) ────────────────────
# These are imported by accounts/views.py

class CryptoWalletSerializer(serializers.ModelSerializer):
    """Read-only representation of a user's crypto wallet."""
    blockchain_display = serializers.CharField(source="get_blockchain_code_display", read_only=True)
    currency_display = serializers.CharField(source="get_currency_code_display", read_only=True)
    short_address = serializers.SerializerMethodField()

    class Meta:
        model = UserCryptoWallet
        fields = [
            "id", "blockchain_code", "blockchain_display",
            "currency_code", "currency_display", "wallet_address",
            "short_address", "is_active", "is_default", "label",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_short_address(self, obj):
        addr = obj.wallet_address
        if len(addr) <= 12:
            return addr
        return f"{addr[:6]}...{addr[-6:]}"


class CryptoWalletCreateSerializer(serializers.ModelSerializer):
    """Create a new wallet for the authenticated user."""

    class Meta:
        model = UserCryptoWallet
        fields = ["blockchain_code", "currency_code", "wallet_address", "label", "is_default"]

    def validate(self, attrs):
        blockchain = attrs.get("blockchain_code")
        currency = attrs.get("currency_code")
        # Validate blockchain/currency pair against PayRam valid pairs
        valid_currencies = VALID_PAYRAM_PAIRS.get(blockchain, [])
        if currency not in valid_currencies:
            raise serializers.ValidationError(
                f"Invalid pair: {blockchain}/{currency}. Valid options: {[(b, c) for b, cs in VALID_PAYRAM_PAIRS.items() for c in cs]}"
            )
        # Validate address format using the function from accounts.serializers
        from apps.accounts.serializers import validate_crypto_address
        attrs["wallet_address"] = validate_crypto_address(blockchain, attrs["wallet_address"])
        return attrs

    def validate_is_default(self, value):
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        # Remove 'user' key if accidentally present (safe guard)
        validated_data.pop('user', None)
        
        is_default = validated_data.pop("is_default", False)

        existing = UserCryptoWallet.objects.filter(
            user=user,
            blockchain_code=validated_data["blockchain_code"],
            currency_code=validated_data["currency_code"]
        ).exists()
        if not existing and not is_default:
            is_default = True

        wallet = UserCryptoWallet.objects.create(user=user, **validated_data)

        if is_default:
            UserCryptoWallet.objects.filter(
                user=user,
                blockchain_code=wallet.blockchain_code,
                currency_code=wallet.currency_code,
                is_default=True
            ).exclude(id=wallet.id).update(is_default=False)
            wallet.is_default = True
            wallet.save(update_fields=["is_default"])

        return wallet


class CryptoWalletUpdateSerializer(serializers.ModelSerializer):
    """Update wallet label, active status, or set as default."""

    class Meta:
        model = UserCryptoWallet
        fields = ["is_active", "is_default", "label"]

    def validate_is_default(self, value):
        return value

    def update(self, instance, validated_data):
        if validated_data.get("is_default", False):
            UserCryptoWallet.objects.filter(
                user=instance.user,
                blockchain_code=instance.blockchain_code,
                currency_code=instance.currency_code,
                is_default=True
            ).exclude(id=instance.id).update(is_default=False)
            instance.is_default = True
            validated_data.pop("is_default", None)
        return super().update(instance, validated_data)