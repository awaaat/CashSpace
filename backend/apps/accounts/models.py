"""
accounts/models.py
==================
Enterprise-grade custom user model for CashSpace.

Supports:
  - Multi-chain / multi-currency crypto wallets (via UserCryptoWallet in payments)
  - Role-based access (User, Support, Admin)
  - Security: login locking, password reset, email verification
  - Full audit logging for all sensitive actions
  - UUID tokens for verification/reset (non-sequential, high entropy)
"""

import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone
from apps.core.models import TimeStampedModel


class UserManager(BaseUserManager):
    """Custom manager for User model with email as primary identifier."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required.")
        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_email_verified", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    """
    CashSpace custom user model.
    Primary identity: email address.
    Crypto wallets are stored in UserCryptoWallet (payments app) — supports multiple
    blockchains and currencies (BTC, ETH, USDT on TRX, etc.).
    """

    class Role(models.TextChoices):
        USER = "user", "User"
        SUPPORT = "support", "Support"
        ADMIN = "admin", "Admin"

    # ── Identity ─────────────────────────────────────────────────────────────
    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)

    # ── Role & Status ────────────────────────────────────────────────────────
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    is_kyc_verified = models.BooleanField(default=False)

    # ── Multi‑chain crypto wallets (now in separate model) ───────────────────
    # The old BTC-only fields are removed. Wallets are accessed via:
    #   user.crypto_wallets.all()   (defined in payments.UserCryptoWallet)
    # To maintain backward compatibility, we add a property method.

    # ── Security ─────────────────────────────────────────────────────────────
    failed_login_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def is_locked(self):
        return bool(self.locked_until and timezone.now() < self.locked_until)

    @property
    def has_any_wallet(self) -> bool:
        """Check if user has at least one active crypto wallet."""
        return self.crypto_wallets.filter(is_active=True).exists()

    def get_default_wallet(self, blockchain_code: str = None, currency_code: str = None):
        """
        Retrieve user's default wallet for a specific blockchain/currency.
        If no default, returns the first active wallet for that pair.
        """
        from apps.payments.models import UserCryptoWallet

        qs = self.crypto_wallets.filter(is_active=True)
        if blockchain_code:
            qs = qs.filter(blockchain_code=blockchain_code)
        if currency_code:
            qs = qs.filter(currency_code=currency_code)
        # Prioritize default wallet
        default = qs.filter(is_default=True).first()
        if default:
            return default
        return qs.first()

    def increment_failed_login(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=30)
        self.save(update_fields=["failed_login_attempts", "locked_until"])

    def reset_failed_login(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        self.save(update_fields=["failed_login_attempts", "locked_until"])


class EmailVerificationToken(models.Model):
    """One-time token sent to user's email to verify their address.
    
    Uses UUID for high entropy; expires after configured time.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="verification_tokens")
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "email_verification_tokens"

    @property
    def is_valid(self):
        return self.used_at is None and timezone.now() < self.expires_at

    def __str__(self):
        return f"VerificationToken for {self.user.email}"


class PasswordResetToken(models.Model):
    """One-time token for password reset flow."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_tokens")
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "password_reset_tokens"

    @property
    def is_valid(self):
        return self.used_at is None and timezone.now() < self.expires_at

    def __str__(self):
        return f"PasswordResetToken for {self.user.email}"


class AuditLog(TimeStampedModel):
    """Immutable audit trail for security-sensitive actions.

    Records all critical operations including multi-wallet changes.
    """

    class Action(models.TextChoices):
        LOGIN = "login", "Login"
        LOGOUT = "logout", "Logout"
        REGISTER = "register", "Register"
        PASSWORD_CHANGE = "password_change", "Password Changed"
        WALLET_ADDED = "wallet_added", "Crypto Wallet Added"
        WALLET_UPDATED = "wallet_updated", "Crypto Wallet Updated"
        WALLET_DELETED = "wallet_deleted", "Crypto Wallet Deleted"
        WALLET_SET_DEFAULT = "wallet_set_default", "Default Wallet Changed"
        PROFILE_UPDATED = "profile_updated", "Profile Updated"
        EMAIL_VERIFIED = "email_verified", "Email Verified"
        ACCOUNT_LOCKED = "account_locked", "Account Locked"
        PAYMENT_INITIATED = "payment_initiated", "Payment Initiated"
        PAYMENT_COMPLETED = "payment_completed", "Payment Completed"
        ADMIN_ACTION = "admin_action", "Admin Action"

    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="audit_logs"
    )
    action = models.CharField(max_length=50, choices=Action.choices, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "audit_logs"
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        indexes = [
            models.Index(fields=["user", "action", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.action} — {self.user} @ {self.created_at:%Y-%m-%d %H:%M}"