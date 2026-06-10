"""
apps/merchants/models.py
========================
Merchant layer for CashSpace — enables high-risk digital businesses
(forex educators, betting tipsters, adult creators, trading communities)
to collect payments without Stripe/PayPal.

Models:
  Merchant              — a user who sells products/access via CashSpace
  Product               — what the merchant is selling (one-time or subscription)
  CustomerCheckout      — identity of the buyer captured before payment
  PostPaymentAction     — what happens automatically after payment is confirmed
  MerchantAPIKey        — test + live keypairs, mode toggle (Stripe-style)
  WebhookDeliveryLog    — every outgoing webhook attempt, response, retry history
"""

import hashlib
import hmac
import secrets
import string
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


# ══════════════════════════════════════════════════════════════════════════════
# KEY GENERATION UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def _generate_api_key(prefix: str) -> str:
    """
    Generate a Stripe-style API key.

    Format: cs_{env}_{type}_{40 random alphanumeric chars}
    Examples:
        cs_test_pk_aB3xZ9...   (publishable test key)
        cs_test_sk_kR7mQ2...   (secret test key)
        cs_live_pk_nT4wL8...   (publishable live key)
        cs_live_sk_yH2pF5...   (secret live key)

    Uses secrets.choice() — cryptographically secure PRNG.
    """
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(40))
    return f"{prefix}_{random_part}"


def _hash_secret_key(raw_key: str) -> str:
    """
    SHA-256 hash a secret key for storage.
    We never store raw secret keys — only the hash.
    Same pattern as how Stripe stores API keys.
    """
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _generate_webhook_secret() -> str:
    """
    Generate a webhook signing secret.
    Format: whsec_<32 random bytes as hex>
    """
    return f"whsec_{secrets.token_hex(32)}"


# ══════════════════════════════════════════════════════════════════════════════
# MERCHANT
# ══════════════════════════════════════════════════════════════════════════════

class Merchant(TimeStampedModel):
    """
    A CashSpace user who sells products/access.

    One User can be both a buyer (existing) and a Merchant.
    Merchants get a public slug used in checkout URLs:
        cashspace.com/pay/<slug>/

    Settlement wallet: where the merchant's payout lands after CashSpace fee.
    If null, falls back to the user's default crypto wallet.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="merchant_profile",
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    business_name = models.CharField(max_length=120)
    slug = models.SlugField(
        max_length=80,
        unique=True,
        help_text="URL-safe identifier: cashspace.com/pay/<slug>/",
    )
    description = models.TextField(
        blank=True,
        help_text="Short description shown on checkout pages",
    )
    logo_url = models.URLField(
        blank=True,
        help_text="Optional logo displayed on checkout",
    )

    # ── Settlement ────────────────────────────────────────────────────────────
    settlement_blockchain = models.CharField(
        max_length=10,
        default="TRX",
        help_text="Blockchain for settlement payout (BTC, ETH, TRX, BASE, POL)",
    )
    settlement_currency = models.CharField(
        max_length=10,
        default="USDT",
        help_text="Currency for settlement payout (BTC, ETH, USDT, USDC, TRX)",
    )
    settlement_wallet_address = models.CharField(
        max_length=100,
        blank=True,
        help_text="Wallet address to receive merchant payouts. Falls back to user default.",
    )

    # ── Commission override ───────────────────────────────────────────────────
    commission_rate_override = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Override global commission rate for this merchant (0.0 to 1.0). Null = use global.",
    )

    # ── Status ────────────────────────────────────────────────────────────────
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive merchants cannot accept new payments",
    )
    is_verified = models.BooleanField(
        default=False,
        help_text="Admin has verified this merchant's business",
    )

    # ── Webhook (merchant-level fallback) ─────────────────────────────────────
    # Merchants can also configure per-product webhooks via PostPaymentAction.
    # This is the catch-all webhook for all payments on this merchant account.
    webhook_url = models.URLField(
        blank=True,
        help_text="POST here when any payment for this merchant is FILLED",
    )
    webhook_secret = models.CharField(
        max_length=120,
        blank=True,
        help_text="HMAC secret for signing merchant webhooks",
    )

    class Meta:
        db_table = "merchants"
        verbose_name = "Merchant"
        verbose_name_plural = "Merchants"

    def __str__(self):
        return f"{self.business_name} (@{self.slug})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.business_name)
            slug = base
            n = 1
            while Merchant.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_effective_commission_rate(self) -> Decimal:
        """Return this merchant's commission rate, falling back to global setting."""
        if self.commission_rate_override is not None:
            return self.commission_rate_override
        return Decimal(str(getattr(settings, "CASHSPACE_COMMISSION_RATE", "0.30")))

    def get_effective_settlement_wallet(self) -> str | None:
        """
        Return the merchant's settlement wallet address.
        Falls back to user's default wallet for the configured blockchain/currency.
        """
        if self.settlement_wallet_address:
            return self.settlement_wallet_address
        default = self.user.get_default_wallet(
            blockchain_code=self.settlement_blockchain,
            currency_code=self.settlement_currency,
        )
        return default.wallet_address if default else None

    @property
    def is_live_mode(self) -> bool:
        """Convenience: True if merchant is operating in live mode."""
        try:
            return not self.api_keys.is_test_mode
        except MerchantAPIKey.DoesNotExist:
            return False


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCT
# ══════════════════════════════════════════════════════════════════════════════

class Product(TimeStampedModel):
    """
    Something a merchant sells — a course, signal subscription, community access, etc.

    Public URL: /pay/<merchant_slug>/<product_slug>/

    price_usd is what the buyer pays. CashSpace takes commission_rate.
    Merchant receives (price_usd * (1 - commission_rate)) in crypto.
    """

    class ProductType(models.TextChoices):
        ONE_TIME = "one_time", "One-time purchase"
        SUBSCRIPTION = "subscription", "Subscription"
        DONATION = "donation", "Donation / Pay what you want"

    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name="products",
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    name = models.CharField(max_length=120)
    slug = models.SlugField(
        max_length=80,
        help_text="URL-safe identifier: /pay/<merchant>/<product>/",
    )
    description = models.TextField(blank=True)

    # ── Pricing ───────────────────────────────────────────────────────────────
    price_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed price in USD. Null for DONATION type (buyer chooses amount).",
    )
    min_price_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=10,
        help_text="Minimum accepted payment (enforced for DONATION type).",
    )
    product_type = models.CharField(
        max_length=20,
        choices=ProductType.choices,
        default=ProductType.ONE_TIME,
    )

    # ── Checkout config ───────────────────────────────────────────────────────
    collect_telegram = models.BooleanField(
        default=False,
        help_text="Ask buyer for their Telegram username at checkout",
    )
    collect_discord = models.BooleanField(
        default=False,
        help_text="Ask buyer for their Discord username at checkout",
    )
    collect_phone = models.BooleanField(
        default=False,
        help_text="Ask buyer for their phone number at checkout",
    )
    collect_custom_field = models.CharField(
        max_length=80,
        blank=True,
        help_text="Label for a custom text field to collect at checkout (e.g. 'Trading account number')",
    )

    # ── Redirect ──────────────────────────────────────────────────────────────
    success_redirect_url = models.URLField(
        blank=True,
        help_text="Redirect buyer here after successful payment (e.g., thank you page)",
    )

    # ── Status ────────────────────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    max_purchases = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Cap total number of purchases. Null = unlimited.",
    )

    class Meta:
        db_table = "merchant_products"
        verbose_name = "Product"
        verbose_name_plural = "Products"
        unique_together = [["merchant", "slug"]]

    def __str__(self):
        return f"{self.merchant.business_name} — {self.name} (${self.price_usd})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            n = 1
            while Product.objects.filter(
                merchant=self.merchant, slug=slug
            ).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def purchase_count(self) -> int:
        return self.customer_checkouts.filter(
            status=CustomerCheckout.Status.COMPLETED
        ).count()

    @property
    def is_sold_out(self) -> bool:
        if self.max_purchases is None:
            return False
        return self.purchase_count >= self.max_purchases

    def get_effective_price(self) -> Decimal | None:
        """Return price for display. None means buyer chooses (DONATION)."""
        return self.price_usd


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMER CHECKOUT
# ══════════════════════════════════════════════════════════════════════════════

class CustomerCheckout(TimeStampedModel):
    """
    Identity of a buyer captured at checkout, before payment.

    This is the core differentiator: merchant knows WHO paid, not just
    that someone paid a wallet address.

    Linked to a Payment after initiation. If payment is abandoned, the
    CustomerCheckout record remains (useful for remarketing).
    """

    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="customer_checkouts",
    )

    # ── Identity fields (always collected) ───────────────────────────────────
    email = models.EmailField(help_text="Buyer's email address")
    full_name = models.CharField(max_length=120, blank=True)

    # ── Optional identity fields ──────────────────────────────────────────────
    telegram_username = models.CharField(max_length=80, blank=True)
    discord_username = models.CharField(max_length=80, blank=True)
    phone_number = models.CharField(max_length=30, blank=True)
    custom_field_value = models.CharField(max_length=255, blank=True)

    # ── Payment link ──────────────────────────────────────────────────────────
    payment = models.OneToOneField(
        "payments.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_checkout",
    )

    # ── Amount ────────────────────────────────────────────────────────────────
    amount_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Amount the buyer agreed to pay",
    )

    # ── Mode snapshot — record whether this was a test or live payment ────────
    is_test = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if this checkout was created in test mode",
    )

    # ── Status ────────────────────────────────────────────────────────────────
    class Status(models.TextChoices):
        INITIATED = "initiated", "Checkout initiated"
        PAYMENT_CREATED = "payment_created", "Payment session created"
        COMPLETED = "completed", "Payment completed"
        ABANDONED = "abandoned", "Checkout abandoned"
        REFUNDED = "refunded", "Refunded"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INITIATED,
        db_index=True,
    )

    # ── Automation ────────────────────────────────────────────────────────────
    automation_triggered = models.BooleanField(default=False)
    automation_triggered_at = models.DateTimeField(null=True, blank=True)
    automation_error = models.TextField(blank=True)

    # ── Metadata ──────────────────────────────────────────────────────────────
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "customer_checkouts"
        verbose_name = "Customer Checkout"
        verbose_name_plural = "Customer Checkouts"
        indexes = [
            models.Index(fields=["product", "status"]),
            models.Index(fields=["email"]),
            models.Index(fields=["telegram_username"]),
            models.Index(fields=["is_test", "status"]),
        ]

    def __str__(self):
        mode = "[TEST]" if self.is_test else "[LIVE]"
        return f"{mode} {self.email} → {self.product.name} (${self.amount_usd}) [{self.status}]"


# ══════════════════════════════════════════════════════════════════════════════
# POST-PAYMENT ACTION
# ══════════════════════════════════════════════════════════════════════════════

class PostPaymentAction(TimeStampedModel):
    """
    What the merchant wants to happen automatically when a payment is FILLED.

    One product can have multiple actions (e.g., add to Telegram AND send email).
    Actions are executed in order (priority ASC).
    """

    class ActionType(models.TextChoices):
        TELEGRAM_INVITE = "telegram_invite", "Telegram group invite"
        DISCORD_ROLE = "discord_role", "Discord role grant"
        EMAIL_DELIVERY = "email_delivery", "Email delivery"
        WEBHOOK = "webhook", "Webhook to merchant"

    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="post_payment_actions",
    )
    action_type = models.CharField(max_length=30, choices=ActionType.choices)
    priority = models.PositiveSmallIntegerField(
        default=0,
        help_text="Actions execute in ascending priority order",
    )
    is_active = models.BooleanField(default=True)
    config = models.JSONField(
        default=dict,
        help_text="Action-specific configuration. See ActionType docstring for keys.",
    )

    class Meta:
        db_table = "post_payment_actions"
        verbose_name = "Post-Payment Action"
        verbose_name_plural = "Post-Payment Actions"
        ordering = ["priority"]

    def __str__(self):
        return f"{self.product.name} → {self.get_action_type_display()} (priority {self.priority})"


# ══════════════════════════════════════════════════════════════════════════════
# MERCHANT API KEYS  (Stripe-style test + live keypairs)
# ══════════════════════════════════════════════════════════════════════════════

class MerchantAPIKey(TimeStampedModel):
    """
    Test + Live keypairs for a merchant. One record per merchant.
    Auto-created via signal when a Merchant is saved for the first time.

    Key types:
        Publishable (pk) — safe to use in frontend JS, identifies the merchant
        Secret (sk)      — server-side only, authorizes API calls

    Storage:
        Publishable keys stored in plaintext (they're not secret).
        Secret keys: only the SHA-256 hash is stored. The raw key is shown
        ONCE at creation/rotation and never retrievable again — same as Stripe.

    Format:
        cs_test_pk_<40chars>
        cs_test_sk_<40chars>   ← shown once, then hashed
        cs_live_pk_<40chars>
        cs_live_sk_<40chars>   ← shown once, then hashed

    Mode:
        is_test_mode = True  → sandbox, no real money moves
        is_test_mode = False → live, real PayRam payments
    """

    merchant = models.OneToOneField(
        Merchant,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )

    # ── Test keypair ──────────────────────────────────────────────────────────
    test_publishable_key = models.CharField(
        max_length=80,
        unique=True,
        help_text="Safe to expose in frontend. Identifies merchant in test mode.",
    )
    test_secret_key_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 hex digest of the test secret key.",
    )
    test_secret_key_prefix = models.CharField(
        max_length=24,
        help_text="First 20 chars for display (e.g. cs_test_sk_aB3xZ9...)",
    )

    # ── Live keypair ──────────────────────────────────────────────────────────
    live_publishable_key = models.CharField(
        max_length=80,
        unique=True,
        help_text="Safe to expose in frontend. Identifies merchant in live mode.",
    )
    live_secret_key_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 hex digest of the live secret key.",
    )
    live_secret_key_prefix = models.CharField(
        max_length=24,
        help_text="First 20 chars for display.",
    )

    # ── Active mode ───────────────────────────────────────────────────────────
    is_test_mode = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True = sandbox mode. False = live mode. Toggle from dashboard.",
    )

    # ── Rotation timestamps ───────────────────────────────────────────────────
    test_key_rotated_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Last time the test secret key was rotated.",
    )
    live_key_rotated_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Last time the live secret key was rotated.",
    )

    class Meta:
        db_table = "merchant_api_keys"
        verbose_name = "Merchant API Keys"
        verbose_name_plural = "Merchant API Keys"

    def __str__(self):
        mode = "TEST" if self.is_test_mode else "LIVE"
        return f"{self.merchant.business_name} — {mode} | pk: {self.test_publishable_key[:24]}..."

    @classmethod
    def create_for_merchant(cls, merchant: "Merchant") -> tuple["MerchantAPIKey", str, str]:
        """
        Generate a fresh keypair for a merchant.

        Returns:
            (MerchantAPIKey instance, raw_test_secret, raw_live_secret)

        The raw secrets are returned ONCE for display. Store them securely
        in the response — they cannot be retrieved again.
        """
        test_pk  = _generate_api_key("cs_test_pk")
        test_sk  = _generate_api_key("cs_test_sk")
        live_pk  = _generate_api_key("cs_live_pk")
        live_sk  = _generate_api_key("cs_live_sk")

        instance = cls.objects.create(
            merchant=merchant,
            test_publishable_key=test_pk,
            test_secret_key_hash=_hash_secret_key(test_sk),
            test_secret_key_prefix=test_sk[:20],
            live_publishable_key=live_pk,
            live_secret_key_hash=_hash_secret_key(live_sk),
            live_secret_key_prefix=live_sk[:20],
            is_test_mode=True,
        )
        return instance, test_sk, live_sk

    def rotate_key(self, env: str) -> str:
        """
        Rotate the secret key for the given environment.

        Args:
            env: "test" or "live"

        Returns:
            The new raw secret key — shown once, never stored in plaintext.
        """
        if env not in ("test", "live"):
            raise ValueError("env must be 'test' or 'live'")

        new_sk = _generate_api_key(f"cs_{env}_sk")

        if env == "test":
            self.test_secret_key_hash   = _hash_secret_key(new_sk)
            self.test_secret_key_prefix = new_sk[:20]
            self.test_key_rotated_at    = timezone.now()
        else:
            self.live_secret_key_hash   = _hash_secret_key(new_sk)
            self.live_secret_key_prefix = new_sk[:20]
            self.live_key_rotated_at    = timezone.now()

        self.save(update_fields=[
            f"{env}_secret_key_hash",
            f"{env}_secret_key_prefix",
            f"{env}_key_rotated_at",
        ])
        return new_sk

    def verify_secret_key(self, raw_key: str) -> bool:
        """
        Verify an incoming secret key against the stored hash.
        Used for API authentication — constant-time comparison.
        """
        if raw_key.startswith("cs_test_"):
            stored_hash = self.test_secret_key_hash
        elif raw_key.startswith("cs_live_"):
            stored_hash = self.live_secret_key_hash
        else:
            return False

        incoming_hash = _hash_secret_key(raw_key)
        return hmac.compare_digest(incoming_hash, stored_hash)

    @property
    def active_publishable_key(self) -> str:
        """Return the publishable key for the current active mode."""
        return self.test_publishable_key if self.is_test_mode else self.live_publishable_key

    @property
    def active_mode_label(self) -> str:
        return "test" if self.is_test_mode else "live"


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK DELIVERY LOG
# ══════════════════════════════════════════════════════════════════════════════

class WebhookDeliveryLog(TimeStampedModel):
    """
    Immutable log of every outgoing webhook attempt to a merchant's endpoint.

    Every time we POST to a merchant's webhook_url (or a PostPaymentAction
    webhook), we record the full attempt here — request body, response code,
    response body, duration, and whether it succeeded.

    This powers:
        - The "Webhook logs" tab in the merchant dashboard
        - Automatic retry logic (up to MAX_ATTEMPTS)
        - Manual retrigger from the dashboard
        - Debugging failed deliveries

    Records are never deleted — append-only for audit purposes.
    """

    MAX_ATTEMPTS = 5
    RETRY_DELAYS = [60, 300, 1800, 7200, 86400]  # 1m, 5m, 30m, 2h, 24h (Stripe-style)

    class EventType(models.TextChoices):
        PAYMENT_COMPLETED   = "payment.completed",   "Payment completed"
        PAYMENT_FAILED      = "payment.failed",      "Payment failed"
        CHECKOUT_INITIATED  = "checkout.initiated",  "Checkout initiated"
        AUTOMATION_FIRED    = "automation.fired",     "Automation fired"
        TEST_WEBHOOK        = "test.webhook",         "Test webhook"

    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        SUCCESS   = "success",   "Success (2xx)"
        FAILED    = "failed",    "Failed (non-2xx or timeout)"
        RETRYING  = "retrying",  "Retrying"
        EXHAUSTED = "exhausted", "Max retries exhausted"

    # ── Relations ─────────────────────────────────────────────────────────────
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.CASCADE,
        related_name="webhook_delivery_logs",
    )
    checkout = models.ForeignKey(
        CustomerCheckout,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_logs",
        help_text="The checkout that triggered this webhook, if applicable.",
    )

    # ── Event ─────────────────────────────────────────────────────────────────
    event_type = models.CharField(
        max_length=40,
        choices=EventType.choices,
        db_index=True,
    )
    is_test = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if fired in test mode.",
    )

    # ── Destination ───────────────────────────────────────────────────────────
    endpoint_url = models.URLField(
        max_length=500,
        help_text="The URL we POSTed to.",
    )

    # ── Request ───────────────────────────────────────────────────────────────
    request_body = models.JSONField(
        help_text="Exact payload we sent.",
    )
    request_headers = models.JSONField(
        default=dict,
        help_text="Headers sent (excluding secrets).",
    )

    # ── Response ──────────────────────────────────────────────────────────────
    response_status_code = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="HTTP status code returned by merchant's server.",
    )
    response_body = models.TextField(
        blank=True,
        help_text="First 2KB of response body.",
    )
    duration_ms = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Round-trip time in milliseconds.",
    )

    # ── Delivery status ───────────────────────────────────────────────────────
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    attempt_number = models.PositiveSmallIntegerField(
        default=1,
        help_text="Which attempt this is (1 = first, 2 = first retry, etc.)",
    )
    next_retry_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the next retry is scheduled.",
    )
    error_message = models.TextField(
        blank=True,
        help_text="Exception or error detail if delivery failed.",
    )

    class Meta:
        db_table = "webhook_delivery_logs"
        verbose_name = "Webhook Delivery Log"
        verbose_name_plural = "Webhook Delivery Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["merchant", "status"]),
            models.Index(fields=["merchant", "event_type"]),
            models.Index(fields=["status", "next_retry_at"]),
        ]

    def __str__(self):
        return (
            f"{self.event_type} → {self.endpoint_url[:40]} "
            f"| {self.status} | attempt {self.attempt_number}"
        )

    @property
    def succeeded(self) -> bool:
        return (
            self.response_status_code is not None
            and 200 <= self.response_status_code < 300
        )

    @property
    def can_retry(self) -> bool:
        return (
            self.status in (self.Status.FAILED, self.Status.RETRYING)
            and self.attempt_number < self.MAX_ATTEMPTS
        )


# ══════════════════════════════════════════════════════════════════════════════
# DJANGO SIGNALS — auto-create API keys on merchant registration
# ══════════════════════════════════════════════════════════════════════════════

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Merchant)
def create_merchant_api_keys(sender, instance, created, **kwargs):
    """
    Automatically generate test + live keypairs when a new Merchant is created.
    The raw secret keys are NOT stored here — they're only accessible at
    creation time via MerchantAPIKey.create_for_merchant().

    For the initial creation we store the keys and emit them via the
    MerchantRegisterView response so the merchant can save them.
    """
    if created and not hasattr(instance, "_skip_api_key_creation"):
        if not MerchantAPIKey.objects.filter(merchant=instance).exists():
            MerchantAPIKey.create_for_merchant(instance) 
            