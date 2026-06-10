# apps/accounts/serializers.py
# Enterprise-grade serializers supporting multi-chain crypto wallets

import re
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AuditLog, User
from apps.payments.models import UserCryptoWallet, Blockchain, Currency, VALID_PAYRAM_PAIRS


# ── Crypto Address Validation (dynamic per blockchain) ───────────────────────

def validate_crypto_address(blockchain_code: str, address: str) -> str:
    """
    Validate wallet address format based on blockchain.
    Returns address if valid, raises ValidationError otherwise.
    """
    if not address:
        return address

    blockchain = blockchain_code.upper()

    # Bitcoin (legacy, P2SH, bech32)
    if blockchain == "BTC":
        pattern = r"^(1[a-km-zA-HJ-NP-Z1-9]{25,34}|3[a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{39,59})$"
        if not re.match(pattern, address):
            raise serializers.ValidationError(
                "Invalid Bitcoin address. Accepted: Legacy (1...), P2SH (3...), or Bech32 (bc1...)."
            )

    # Ethereum, Base, Polygon (EVM chains: 0x-prefixed hex, 40 chars after 0x)
    elif blockchain in ["ETH", "BASE", "POL"]:
        pattern = r"^0x[a-fA-F0-9]{40}$"
        if not re.match(pattern, address):
            raise serializers.ValidationError(f"Invalid {blockchain} address. Must be 0x-prefixed 40 hex chars.")

    # Tron (base58, length ~34)
    elif blockchain == "TRX":
        pattern = r"^[A-Za-z0-9]{34}$"
        if not re.match(pattern, address):
            raise serializers.ValidationError("Invalid TRON address. Must be 34 alphanumeric characters (base58).")

    else:
        # Unknown blockchain – accept but log warning (enterprise: add to validation registry)
        pass

    return address


# ── Auth Serializers (unchanged except token payload) ────────────────────────

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ["email", "first_name", "last_name", "password", "password_confirm"]

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends JWT token to include user profile and multi-wallet awareness.
    """

    def validate(self, attrs):
        # Check account lock before authentication
        try:
            user = User.objects.get(email=attrs.get("email", "").lower())
            if user.is_locked:
                raise serializers.ValidationError(
                    {
                        "detail": f"Account locked until {user.locked_until.strftime('%H:%M UTC')} "
                                  "due to failed attempts."
                    }
                )
        except User.DoesNotExist:
            pass

        data = super().validate(attrs)
        data["user"] = UserProfileSerializer(self.user).data
        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        token["role"] = user.role
        token["has_any_wallet"] = user.has_any_wallet
        return token


# ── Crypto Wallet Serializers (new) ──────────────────────────────────────────

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
        # Validate address format for this blockchain
        attrs["wallet_address"] = validate_crypto_address(blockchain, attrs["wallet_address"])
        return attrs

    def validate_is_default(self, value):
        # If setting this wallet as default, we'll handle uniqueness in view to avoid race conditions
        return value

    def create(self, validated_data):
        user = self.context["request"].user
        is_default = validated_data.pop("is_default", False)

        # If this is the first wallet for this user for this (blockchain, currency), auto-set default
        existing = UserCryptoWallet.objects.filter(
            user=user,
            blockchain_code=validated_data["blockchain_code"],
            currency_code=validated_data["currency_code"]
        ).exists()
        if not existing and not is_default:
            is_default = True

        wallet = UserCryptoWallet.objects.create(user=user, **validated_data)

        if is_default:
            # Unset other defaults for same (user, blockchain, currency)
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
        # If setting default, we'll handle in update
        return value

    def update(self, instance, validated_data):
        if validated_data.get("is_default", False):
            # Remove default from other wallets for same (user, blockchain, currency)
            UserCryptoWallet.objects.filter(
                user=instance.user,
                blockchain_code=instance.blockchain_code,
                currency_code=instance.currency_code,
                is_default=True
            ).exclude(id=instance.id).update(is_default=False)
            instance.is_default = True
            validated_data.pop("is_default", None)
        return super().update(instance, validated_data)


# ── User Profile Serializers (updated) ───────────────────────────────────────

class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    has_any_wallet = serializers.ReadOnlyField()
    crypto_wallets = CryptoWalletSerializer(many=True, read_only=True)
    default_wallet_info = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "phone_number",
            "avatar",
            "role",
            "is_email_verified",
            "is_kyc_verified",
            "has_any_wallet",
            "crypto_wallets",
            "default_wallet_info",
            "date_joined",
        ]
        read_only_fields = [
            "id", "email", "role", "is_email_verified",
            "is_kyc_verified", "date_joined",
        ]

    def get_default_wallet_info(self, obj):
        """Return a mapping of blockchain/currency pairs to default wallet address."""
        defaults = {}
        for wallet in obj.crypto_wallets.filter(is_active=True, is_default=True):
            key = f"{wallet.blockchain_code}_{wallet.currency_code}"
            defaults[key] = {
                "blockchain": wallet.blockchain_code,
                "currency": wallet.currency_code,
                "address": wallet.wallet_address,
                "label": wallet.label,
            }
        return defaults


class UpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone_number", "avatar"]


# DEPRECATED: UpdateWalletSerializer removed – replaced by crypto wallet endpoints


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs.pop("new_password_confirm"):
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        return attrs

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.UUIDField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs.pop("new_password_confirm"):
            raise serializers.ValidationError({"new_password_confirm": "Passwords do not match."})
        return attrs


# ── Admin Serializers (updated to remove BTC-specific fields) ────────────────

class AdminUserListSerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    transaction_count = serializers.SerializerMethodField()
    has_any_wallet = serializers.ReadOnlyField()
    wallet_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "full_name", "role", "is_active",
            "is_email_verified", "is_kyc_verified", "has_any_wallet",
            "wallet_count", "last_login", "date_joined", "transaction_count",
        ]

    def get_transaction_count(self, obj):
        return obj.payments.count()

    def get_wallet_count(self, obj):
        return obj.crypto_wallets.filter(is_active=True).count()


class AdminUserDetailSerializer(serializers.ModelSerializer):
    """Full read/write access for staff."""
    full_name = serializers.ReadOnlyField()
    crypto_wallets = CryptoWalletSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name",
            "phone_number", "role", "is_active", "is_staff",
            "is_email_verified", "is_kyc_verified",
            "crypto_wallets",  # replaces btc_wallet_address
            "failed_login_attempts", "locked_until",
            "last_login", "last_login_ip", "date_joined",
        ]
        read_only_fields = ["id", "email", "last_login", "last_login_ip", "date_joined"]


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True, default="deleted")

    class Meta:
        model = AuditLog
        fields = ["id", "user_email", "action", "ip_address", "metadata", "created_at"]