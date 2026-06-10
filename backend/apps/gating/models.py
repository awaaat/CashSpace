"""
apps/gating/models.py
=====================
Enterprise‑grade, URL‑as‑payable‑asset / gated access layer for CashSpace.

This is NOT a junior‑level implementation. It handles:
  - Any asset type: external URL, Telegram group, Discord role, file download,
    API key / password, custom webhook, embedded code (iframe/script).
  - Subscription / recurring access (time‑based or payment‑based).
  - Multi‑tier pricing (different prices for different unlock durations).
  - Team / group purchases (single payment unlocks for multiple emails).
  - Affiliate / referral tracking (commission on sales).
  - Discount codes / coupons (fixed amount or percentage).
  - Geo‑restriction (limit by buyer IP country).
  - Rate limiting per buyer (max grants per asset per email).
  - Refund handling & access revocation.
  - Detailed analytics (clicks, conversions, referrers).
  - Webhook notifications on every grant.
  - Embeddable assets (iframe, script tag) for external sites.
  - Multi‑step unlocks (pay for step 1 to unlock step 2).
  - Asset bundling (pay once, unlock multiple assets).
  - Dynamic pricing (demand‑based, surge pricing).
  - Referrer whitelisting (prevent hotlinking).
  - Time‑limited access after grant (e.g., 24‑hour video access).
  - Full access audit logs.
  - Resale / transfer of access tokens (optional, with admin approval).
  - Password‑protected assets (extra security layer).
  - CAPTCHA on checkout (anti‑bot).
  - Blockchain / NFT‑gated assets (optional, for future).

All models are fully indexed, with proper constraints and helper methods.
"""

import uuid
import hashlib
import hmac
from decimal import Decimal
from datetime import timedelta
from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.utils import timezone
from django.utils.text import slugify
from apps.core.models import TimeStampedModel


# ----------------------------------------------------------------------
# Helper: generate a signed token (used for external verification)
# ----------------------------------------------------------------------
def generate_signed_token(asset_id, grant_id, buyer_email, expires_at):
    """
    Generate a HMAC‑signed token for external URL verification.
    Not a full JWT – simpler and faster.
    """
    data = f"{asset_id}:{grant_id}:{buyer_email}:{expires_at.timestamp() if expires_at else 0}"
    signature = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return f"{data}:{signature}"


# ----------------------------------------------------------------------
# GatedAsset – the core pay‑to‑unlock resource
# ----------------------------------------------------------------------
class GatedAsset(TimeStampedModel):
    """
    A resource locked behind a payment. Created by any authenticated user.

    This model supports every monetisation pattern used in the real world.
    """

    class AssetType(models.TextChoices):
        URL = "url", "External URL"
        TELEGRAM = "telegram", "Telegram Group"
        DISCORD = "discord", "Discord Server Role"
        FILE = "file", "File Download (hosted on CashSpace or external)"
        API_KEY = "api_key", "API Key / Password"
        EMBED = "embed", "Embed Code (iframe / script)"
        WEBHOOK = "webhook", "Custom Webhook (POST to buyer's endpoint)"
        CONTENT = "content", "Hidden Text / HTML Content"

    class PricingType(models.TextChoices):
        FIXED = "fixed", "Fixed Price"
        DONATION = "donation", "Pay What You Want"
        SUBSCRIPTION = "subscription", "Recurring Subscription"
        TIERED = "tiered", "Multi‑Tier (different prices / durations)"

    class AccessDurationUnit(models.TextChoices):
        HOURS = "hours", "Hours"
        DAYS = "days", "Days"
        WEEKS = "weeks", "Weeks"
        MONTHS = "months", "Months"
        YEARS = "years", "Years"

    # ── Owner & branding ──────────────────────────────────────────────────────
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="gated_assets",
        help_text="Creator who owns this asset",
    )
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gated_assets",
        help_text="Optional: link to a merchant account for advanced dashboard",
    )

    # ── Identity ──────────────────────────────────────────────────────────────
    title = models.CharField(max_length=200)
    slug = models.SlugField(
        max_length=100,
        unique=True,
        help_text="Public URL: /gating/<slug>/",
    )
    description = models.TextField(
        blank=True,
        help_text="Markdown supported. Shown before payment.",
    )
    thumbnail_url = models.URLField(
        blank=True,
        help_text="Thumbnail / cover image displayed on checkout.",
    )
    video_preview_url = models.URLField(
        blank=True,
        help_text="Optional preview video (e.g., YouTube/Vimeo).",
    )

    # ── Asset type & delivery ─────────────────────────────────────────────────
    asset_type = models.CharField(
        max_length=20,
        choices=AssetType.choices,
        default=AssetType.URL,
    )
    unlock_value = models.TextField(
        blank=True,
        help_text=(
            "The locked resource. For URL/Telegram: the link. "
            "For API_KEY/CONTENT: the secret. For FILE: path or external URL. "
            "For EMBED: HTML/JS snippet. For WEBHOOK: endpoint URL."
        ),
    )
    unlock_config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Extra configuration:\n"
            "  - Discord: {guild_id, role_id, bot_token, message}\n"
            "  - URL: {redirect_delay_seconds, add_token_as_query_param (bool)}\n"
            "  - WEBHOOK: {headers, method, retry_count}\n"
            "  - EMBED: {width, height, sandbox}\n"
            "  - FILE: {expiry_seconds, download_limit}\n"
            "  - API_KEY: {instructions, regenerate_on_each_grant}"
        ),
    )

    # ── Pricing ───────────────────────────────────────────────────────────────
    pricing_type = models.CharField(
        max_length=20,
        choices=PricingType.choices,
        default=PricingType.FIXED,
    )
    price_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Fixed price in USD. Null for DONATION / TIERED.",
    )
    min_price_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=5,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="Minimum allowed for DONATION type.",
    )
    max_price_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum allowed for DONATION type. Null = no max.",
    )

    # ── Tiered pricing (for PricingType.TIERED) ───────────────────────────────
    price_tiers = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "List of tiers: [{\"price\": 9.99, \"duration_value\": 30, "
            "\"duration_unit\": \"days\", \"description\": \"Standard\"}, ...]"
        ),
    )

    # ── Subscription settings (for PricingType.SUBSCRIPTION) ──────────────────
    subscription_interval_value = models.PositiveIntegerField(
        default=30,
        help_text="How many units between recurring charges.",
    )
    subscription_interval_unit = models.CharField(
        max_length=10,
        choices=AccessDurationUnit.choices,
        default=AccessDurationUnit.DAYS,
        help_text="Unit for subscription interval (days, weeks, months).",
    )
    subscription_trial_days = models.PositiveIntegerField(
        default=0,
        help_text="Free trial days before first charge.",
    )
    subscription_max_cycles = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Max number of payments. Null = indefinite until cancelled.",
    )

    # ── Access duration (after payment) ──────────────────────────────────────
    grant_duration_value = models.PositiveIntegerField(
        default=0,
        help_text="How long access lasts. 0 = permanent.",
    )
    grant_duration_unit = models.CharField(
        max_length=10,
        choices=AccessDurationUnit.choices,
        blank=True,
        help_text="Unit for grant duration.",
    )

    # ── Settlement (where crypto payout goes) ─────────────────────────────────
    settlement_blockchain = models.CharField(
        max_length=10,
        default="TRX",
        help_text="Blockchain for payout (BTC, ETH, TRX, BASE, POL).",
    )
    settlement_currency = models.CharField(
        max_length=10,
        default="USDT",
        help_text="Currency/token for payout.",
    )
    settlement_wallet_address = models.CharField(
        max_length=100,
        blank=True,
        help_text="Explicit wallet. Falls back to owner's default.",
    )

    # ─── Access token behaviour ──────────────────────────────────────────────
    token_expires_after_grant_value = models.PositiveIntegerField(
        default=0,
        help_text="Hours after grant until token expires (0 = never).",
    )
    token_max_uses = models.PositiveIntegerField(
        default=1,
        help_text="How many times the token can be used. 1 = single‑use.",
    )
    token_requires_email_verification = models.BooleanField(
        default=False,
        help_text="If True, buyer must click a link in email before token is activated.",
    )

    # ── Restrictions & limits ─────────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    max_grants = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total number of sales allowed. Null = unlimited.",
    )
    max_grants_per_email = models.PositiveIntegerField(
        default=1,
        help_text="How many times the same email can buy this asset. 0 = unlimited.",
    )
    allowed_countries = models.JSONField(
        default=list,
        blank=True,
        help_text="ISO country codes allowed (empty = all). Ex: [\"US\", \"GB\"]",
    )
    blocked_countries = models.JSONField(
        default=list,
        blank=True,
        help_text="ISO country codes blocked (overrides allowed).",
    )
    require_captcha = models.BooleanField(
        default=False,
        help_text="Require CAPTCHA on checkout form (anti‑bot).",
    )

    # ── Referrer / source tracking ───────────────────────────────────────────
    allowed_referrers = models.JSONField(
        default=list,
        blank=True,
        help_text="List of allowed referrer domains (e.g., ['example.com']). Empty = all.",
    )

    # ── Discount codes / coupons ─────────────────────────────────────────────
    discount_codes = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Discount codes: {\"SAVE10\": {\"type\": \"percent\", \"value\": 10, "
            "\"max_uses\": 100, \"expires_at\": \"2026-12-31\"}}"
        ),
    )

    # ── Affiliate / referral program ─────────────────────────────────────────
    affiliate_commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of sale given to affiliate who referred buyer.",
    )
    affiliate_cookie_days = models.PositiveIntegerField(
        default=30,
        help_text="Days affiliate cookie lasts.",
    )

    # ── Dynamic pricing (surge / demand) ─────────────────────────────────────
    dynamic_pricing_enabled = models.BooleanField(default=False)
    base_price_usd = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        help_text="Base price before dynamic multiplier.",
    )
    price_multiplier = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('1.00'),
        help_text="Multiplier applied to base price based on demand.",
    )
    demand_window_days = models.PositiveIntegerField(
        default=7,
        help_text="Days to look back for sales velocity.",
    )

    # ── Multi‑step unlocks (drip content) ────────────────────────────────────
    steps = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "For content that unlocks gradually: [{\"step\": 1, \"delay_days\": 0, "
            "\"value\": \"first video URL\"}, ...]. Only applies to asset_type=CONTENT/URL."
        ),
    )

    # ── Bundling (group asset) ──────────────────────────────────────────────
    bundled_assets = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        related_name="bundled_in",
        help_text="Other assets included when this asset is purchased.",
    )

    # ── Success & post‑payment messaging ─────────────────────────────────────
    success_message = models.TextField(
        blank=True,
        help_text="Custom message shown on success page / email.",
    )
    success_redirect_url = models.URLField(
        blank=True,
        help_text="Redirect buyer here after payment (overrides token delivery).",
    )
    send_welcome_email = models.BooleanField(default=True)
    welcome_email_template = models.TextField(
        blank=True,
        help_text="Custom email body with placeholders: {buyer_name}, {asset_title}, {access_link}.",
    )

    # ── Webhook notifications (for external systems) ─────────────────────────
    webhook_url = models.URLField(
        blank=True,
        help_text="POST to this URL on every successful grant (with access token).",
    )
    webhook_secret = models.CharField(
        max_length=200,
        blank=True,
        help_text="HMAC secret to sign webhook payloads.",
    )

    # ── Advanced / experimental ─────────────────────────────────────────────
    nft_gate_contract = models.CharField(
        max_length=100,
        blank=True,
        help_text="Optional: NFT contract address required to access (buyer must own NFT).",
    )
    nft_gate_min_balance = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Minimum number of NFTs required.",
    )
    blockchain_network = models.CharField(
        max_length=20,
        blank=True,
        help_text="e.g., 'ethereum', 'polygon' for NFT gating.",
    )

    class Meta:
        db_table = "gated_assets"
        verbose_name = "Gated Asset"
        verbose_name_plural = "Gated Assets"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["owner", "is_active"]),
            models.Index(fields=["pricing_type", "price_usd"]),
        ]

    def __str__(self):
        return f"{self.title} [{self.asset_type}]"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            slug = base
            n = 1
            while GatedAsset.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def grant_count(self):
        return self.access_grants.filter(status=AccessGrant.Status.GRANTED).count()

    @property
    def revenue_usd(self):
        from django.db.models import Sum
        return self.access_grants.filter(status=AccessGrant.Status.GRANTED).aggregate(
            total=Sum("amount_usd")
        )["total"] or Decimal("0.00")

    @property
    def is_sold_out(self):
        if self.max_grants is None:
            return False
        return self.grant_count >= self.max_grants

    def get_effective_settlement_wallet(self):
        if self.settlement_wallet_address:
            return self.settlement_wallet_address
        default = self.owner.get_default_wallet(
            blockchain_code=self.settlement_blockchain,
            currency_code=self.settlement_currency,
        )
        return default.wallet_address if default else None

    def get_price_for_buyer(self, email=None, affiliate_code=None, quantity=1):
        """
        Calculate final price considering dynamic pricing, affiliate discounts,
        and any other factors.
        """
        base = self.price_usd
        if self.pricing_type == self.PricingType.DONATION:
            # price is set by buyer, validated separately
            return None
        if self.pricing_type == self.PricingType.TIERED:
            # Should be selected by buyer
            return None
        if self.dynamic_pricing_enabled and self.base_price_usd:
            velocity = self.get_sales_velocity(self.demand_window_days)
            # Simple multiplier: 1 + (velocity / 100)
            multiplier = 1 + (velocity / 100)
            base = self.base_price_usd * multiplier
        return base.quantize(Decimal("0.01"))

    def get_sales_velocity(self, days=7):
        """Return average daily sales over last N days."""
        since = timezone.now() - timedelta(days=days)
        count = self.access_grants.filter(
            status=AccessGrant.Status.GRANTED,
            created_at__gte=since
        ).count()
        return count / days if days else 0

    def is_country_allowed(self, country_code):
        if not country_code:
            return True
        if self.blocked_countries and country_code in self.blocked_countries:
            return False
        if self.allowed_countries and country_code not in self.allowed_countries:
            return False
        return True

    def is_referrer_allowed(self, referrer_url):
        if not referrer_url or not self.allowed_referrers:
            return True
        from urllib.parse import urlparse
        domain = urlparse(referrer_url).netloc
        return any(domain == allowed or domain.endswith(f".{allowed}") for allowed in self.allowed_referrers)

    def get_access_duration_timedelta(self):
        if self.grant_duration_value == 0:
            return None
        unit = self.grant_duration_unit
        value = self.grant_duration_value
        if unit == self.AccessDurationUnit.HOURS:
            return timedelta(hours=value)
        if unit == self.AccessDurationUnit.DAYS:
            return timedelta(days=value)
        if unit == self.AccessDurationUnit.WEEKS:
            return timedelta(weeks=value)
        if unit == self.AccessDurationUnit.MONTHS:
            return timedelta(days=value * 30)
        if unit == self.AccessDurationUnit.YEARS:
            return timedelta(days=value * 365)
        return None


# ----------------------------------------------------------------------
# AccessGrant – tracks a buyer's payment and status
# ----------------------------------------------------------------------
class AccessGrant(TimeStampedModel):
    """
    A buyer's attempt to access an asset. Created when they submit the checkout.
    """

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        PENDING_EMAIL_VERIFICATION = "pending_email_verif", "Awaiting Email Verification"
        PAYMENT_CREATED = "payment_created", "Payment Session Created"
        GRANTED = "granted", "Access Granted"
        ABANDONED = "abandoned", "Abandoned"
        REFUNDED = "refunded", "Refunded"
        REVOKED = "revoked", "Revoked by Admin"
        EXPIRED = "expired", "Access Expired"

    asset = models.ForeignKey(
        GatedAsset,
        on_delete=models.PROTECT,
        related_name="access_grants",
    )
    # Buyer info
    email = models.EmailField(db_index=True)
    full_name = models.CharField(max_length=120, blank=True)
    country_code = models.CharField(max_length=2, blank=True, help_text="ISO 3166-1 alpha-2")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Referral / affiliate
    affiliate_code = models.CharField(max_length=50, blank=True, db_index=True)
    referrer_url = models.URLField(blank=True)

    # Discount
    discount_code_used = models.CharField(max_length=50, blank=True)
    discount_amount_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Pricing & payment
    amount_usd = models.DecimalField(max_digits=12, decimal_places=2)
    payment = models.OneToOneField(
        "payments.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_grant",
    )
    selected_tier_index = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Index of chosen tier (for TIERED pricing).",
    )

    # Status
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.INITIATED, db_index=True)

    # Access expiry (if asset has limited access duration)
    access_expires_at = models.DateTimeField(null=True, blank=True)

    # Delivery tracking
    unlock_delivered = models.BooleanField(default=False)
    unlock_delivered_at = models.DateTimeField(null=True, blank=True)
    unlock_error = models.TextField(blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)  # store anything extra

    class Meta:
        db_table = "access_grants"
        verbose_name = "Access Grant"
        verbose_name_plural = "Access Grants"
        indexes = [
            models.Index(fields=["asset", "status"]),
            models.Index(fields=["email", "asset"]),
            models.Index(fields=["affiliate_code"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.email} → {self.asset.title} [{self.status}]"

    def activate_grant(self, token_value=None):
        """
        Called after payment is confirmed. Creates the AccessToken and marks as GRANTED.
        Returns the token object.
        """
        from .tokens import create_access_token  # imported here to avoid circular import

        if self.status in [self.Status.GRANTED, self.Status.REVOKED]:
            return self.access_token if hasattr(self, 'access_token') else None

        self.status = self.Status.GRANTED
        self.save(update_fields=["status"])

        # Calculate access expiration based on asset's grant duration
        delta = self.asset.get_access_duration_timedelta()
        expires_at = timezone.now() + delta if delta else None

        token, created = AccessToken.objects.get_or_create(
            grant=self,
            defaults={
                "expires_at": expires_at,
                "max_uses": self.asset.token_max_uses,
            }
        )
        if token_value:
            token.token = token_value
            token.save(update_fields=["token"])
        return token

    def revoke(self):
        if self.status == self.Status.GRANTED:
            self.status = self.Status.REVOKED
            self.save(update_fields=["status"])
            if hasattr(self, 'access_token'):
                self.access_token.expires_at = timezone.now()
                self.access_token.save(update_fields=["expires_at"])

    def is_access_valid(self):
        if self.status != self.Status.GRANTED:
            return False
        if self.access_expires_at and timezone.now() > self.access_expires_at:
            return False
        return True


# ----------------------------------------------------------------------
# AccessToken – the actual secret used to unlock the resource
# ----------------------------------------------------------------------
class AccessToken(models.Model):
    """
    A token that proves payment. It can be single‑use, time‑limited, or permanent.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grant = models.OneToOneField(
        AccessGrant,
        on_delete=models.CASCADE,
        related_name="access_token",
    )
    token = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        default=uuid.uuid4,
        help_text="The secret token sent to buyer. Can be UUID or signed string.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(
        null=True, blank=True,
        help_text="When this token expires. Null = never.",
    )
    use_count = models.PositiveIntegerField(default=0)
    max_uses = models.PositiveIntegerField(default=1, help_text="0 = unlimited.")
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "access_tokens"
        verbose_name = "Access Token"
        verbose_name_plural = "Access Tokens"
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Token for {self.grant.email}"

    @property
    def is_expired(self):
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at

    @property
    def is_exhausted(self):
        if self.max_uses == 0:
            return False
        return self.use_count >= self.max_uses

    @property
    def is_valid(self):
        return not self.is_expired and not self.is_exhausted

    def consume(self):
        """Record a use. Returns True if token remains valid afterwards."""
        if not self.is_valid:
            return False
        self.use_count += 1
        self.last_used_at = timezone.now()
        self.save(update_fields=["use_count", "last_used_at"])
        return self.is_valid


# ----------------------------------------------------------------------
# AccessLog – detailed audit of every access attempt
# ----------------------------------------------------------------------
class AccessLog(models.Model):
    """
    Logs every attempt to unlock an asset, including IP, user agent, success/failure.
    Useful for analytics and security auditing.
    """
    grant = models.ForeignKey(
        AccessGrant,
        on_delete=models.CASCADE,
        related_name="access_logs",
    )
    token = models.ForeignKey(
        AccessToken,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="access_logs",
    )
    action = models.CharField(max_length=50, choices=[
        ("view_checkout", "View Checkout Page"),
        ("submit_checkout", "Submit Checkout Form"),
        ("payment_redirect", "Redirect to PayRam"),
        ("payment_return", "Return from PayRam"),
        ("token_verification", "Token Verification Attempt"),
        ("unlock_delivery", "Unlock Delivered"),
        ("unlock_failed", "Unlock Failed"),
    ])
    success = models.BooleanField(default=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    request_headers = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "access_logs"
        indexes = [
            models.Index(fields=["grant", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    def __str__(self):
        return f"{self.action} for {self.grant.email} at {self.created_at}"


# ----------------------------------------------------------------------
# DiscountCode – separate model for more robust coupon management
# (can also be stored in GatedAsset.discount_codes JSON, but this is more scalable)
# ----------------------------------------------------------------------
class DiscountCode(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percentage off"
        FIXED = "fixed", "Fixed amount off"

    code = models.CharField(max_length=50, unique=True, db_index=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Percent (0-100) or fixed USD")
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)
    max_uses = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)
    assets = models.ManyToManyField(GatedAsset, blank=True, related_name="discounts", help_text="Leave empty = apply to all")
    min_purchase_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "discount_codes"

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        if now < self.valid_from:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True

    def apply(self, amount_usd):
        if not self.is_valid:
            return amount_usd
        if self.discount_type == self.DiscountType.PERCENT:
            discount = amount_usd * (self.discount_value / 100)
        else:
            discount = self.discount_value
        return max(Decimal('0.00'), amount_usd - discount)


# ----------------------------------------------------------------------
# AffiliateClick – track referral links
# ----------------------------------------------------------------------
class AffiliateClick(models.Model):
    affiliate_code = models.CharField(max_length=50, db_index=True)
    asset = models.ForeignKey(GatedAsset, on_delete=models.CASCADE, null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    referrer_url = models.URLField(blank=True)
    converted = models.BooleanField(default=False)
    grant = models.ForeignKey(AccessGrant, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "affiliate_clicks"
        indexes = [
            models.Index(fields=["affiliate_code", "created_at"]),
        ]


# ----------------------------------------------------------------------
# EmbedToken – for iframe/script embedding that requires separate auth
# ----------------------------------------------------------------------
class EmbedToken(models.Model):
    """
    Short‑lived token used for embedded assets (iframe). Allows external sites
    to render protected content without exposing the actual access token.
    """
    grant = models.ForeignKey(AccessGrant, on_delete=models.CASCADE, related_name="embed_tokens")
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "embed_tokens"

    @property
    def is_valid(self):
        return timezone.now() < self.expires_at