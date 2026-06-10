"""
apps/creator/models.py
======================
Advanced creator backend for CashSpace.

Creators (any authenticated user) can:
  - Create payable assets (URLs, files, content, API keys, Telegram invites, Discord roles)
  - Set multiple pricing models (fixed, subscription, tiered, pay-what-you-want)
  - Configure access duration (1 hour to permanent)
  - Track detailed analytics (views, conversions, revenue by source)
  - Use discount codes and affiliate programs
  - Set up webhooks for external notifications
  - Embed unlock widgets on their own site
  - Receive payouts to their preferred crypto wallet (USDT, BTC, ETH, etc.)

All payments go through CashSpace, which takes a commission (30% default,
configurable per creator or per asset). The creator's net amount is automatically
calculated and recorded for each sale.

This model layer is designed to be used by the creator frontend dashboard,
but also exposes a public API for embedded checkouts.
"""

import uuid
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator, URLValidator
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


class CreatorProfile(models.Model):
    """
    Extended profile for a user who sells digital goods.
    Automatically created when user first creates a payable asset.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="creator_profile",
    )
    display_name = models.CharField(max_length=100, blank=True)
    bio = models.TextField(blank=True, help_text="Public bio shown on your creator page")
    avatar_url = models.URLField(blank=True)
    cover_image_url = models.URLField(blank=True)
    website = models.URLField(blank=True)
    twitter_handle = models.CharField(max_length=50, blank=True)
    telegram_handle = models.CharField(max_length=50, blank=True)

    # Custom settlement wallet (if not using user's default)
    custom_payout_wallet = models.CharField(max_length=100, blank=True)
    custom_payout_blockchain = models.CharField(max_length=10, blank=True, default="TRX")
    custom_payout_currency = models.CharField(max_length=10, blank=True, default="USDT")

    # Override global commission rate for this creator (0.0 to 1.0)
    commission_rate_override = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
        help_text="Override global commission for this creator. Null = use global."
    )

    # Verification status (admin approved)
    is_verified = models.BooleanField(default=False)
    verification_docs = models.JSONField(default=list, blank=True)

    # Limits
    max_assets = models.PositiveIntegerField(default=100)
    max_monthly_sales = models.PositiveIntegerField(default=1000)

    # Analytics
    total_views = models.PositiveIntegerField(default=0)
    total_sales = models.PositiveIntegerField(default=0)
    total_revenue_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "creator_profiles"

    def __str__(self):
        return f"Creator: {self.user.email}"

    def get_effective_commission_rate(self):
        if self.commission_rate_override is not None:
            return self.commission_rate_override
        from django.conf import settings
        return Decimal(str(getattr(settings, "CASHSPACE_COMMISSION_RATE", "0.30")))

    def get_payout_wallet(self):
        if self.custom_payout_wallet:
            return self.custom_payout_wallet
        default = self.user.get_default_wallet(
            blockchain_code=self.custom_payout_blockchain or "TRX",
            currency_code=self.custom_payout_currency or "USDT",
        )
        return default.wallet_address if default else None


class PayableAsset(TimeStampedModel):
    """
    A digital asset that can be sold by a creator.
    This is the core model – a pay‑to‑unlock resource.
    """
    class AssetType(models.TextChoices):
        URL = "url", "External URL (course, video, private page)"
        FILE = "file", "File Download (PDF, ZIP, MP4)"
        CONTENT = "content", "Hidden Text / HTML"
        API_KEY = "api_key", "API Key / License Key"
        TELEGRAM = "telegram", "Telegram Group Invite"
        DISCORD = "discord", "Discord Role Grant"
        EMBED = "embed", "Embeddable Widget (iframe/script)"

    class PricingType(models.TextChoices):
        FIXED = "fixed", "Fixed Price"
        PAY_WHAT_YOU_WANT = "pwyw", "Pay What You Want"
        SUBSCRIPTION = "subscription", "Recurring Subscription"
        TIERED = "tiered", "Multi‑Tier Pricing"

    class AccessDuration(models.TextChoices):
        PERMANENT = "permanent", "Permanent"
        HOURS = "hours", "Hours"
        DAYS = "days", "Days"
        WEEKS = "weeks", "Weeks"
        MONTHS = "months", "Months"
        YEARS = "years", "Years"

    # ── Identity ──────────────────────────────────────────────────────────
    creator = models.ForeignKey(CreatorProfile, on_delete=models.CASCADE, related_name="assets")
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True, help_text="Markdown supported")
    thumbnail_url = models.URLField(blank=True)
    video_preview_url = models.URLField(blank=True, help_text="YouTube/Vimeo preview")

    # ── Asset type & locked content ──────────────────────────────────────
    asset_type = models.CharField(max_length=20, choices=AssetType.choices, default=AssetType.URL)
    unlock_value = models.TextField(help_text="The URL, file path, secret, or invite link")
    unlock_config = models.JSONField(default=dict, blank=True, help_text="""
        Extra config for advanced types:
        - discord: {"guild_id": "...", "role_id": "...", "bot_token": "..."}
        - url: {"redirect_delay": 0, "add_token": true}
        - file: {"expiry_seconds": 3600, "max_downloads": 3}
        - embed: {"width": 800, "height": 600}
    """)

    # ── Pricing ──────────────────────────────────────────────────────────
    pricing_type = models.CharField(max_length=20, choices=PricingType.choices, default=PricingType.FIXED)
    price_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_price_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("5.00"))
    max_price_usd = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Tiered pricing: list of {"price": 9.99, "duration_days": 30, "description": "Standard"}
    price_tiers = models.JSONField(default=list, blank=True)

    # Subscription (if applicable)
    subscription_interval_days = models.PositiveIntegerField(default=30, help_text="Billing interval in days")
    subscription_trial_days = models.PositiveIntegerField(default=0)
    subscription_max_cycles = models.PositiveIntegerField(default=0, help_text="0 = indefinite")

    # Access duration after purchase
    access_duration_value = models.PositiveIntegerField(default=0)
    access_duration_unit = models.CharField(max_length=10, choices=AccessDuration.choices, default=AccessDuration.PERMANENT)

    # ── Limits & restrictions ────────────────────────────────────────────
    is_active = models.BooleanField(default=True)
    max_sales = models.PositiveIntegerField(null=True, blank=True, help_text="Max total sales (null = unlimited)")
    max_sales_per_buyer = models.PositiveIntegerField(default=1, help_text="Per email address")
    allowed_countries = models.JSONField(default=list, blank=True, help_text="ISO codes, empty = all")
    require_captcha = models.BooleanField(default=False)

    # ── Settlement (payout to creator) ────────────────────────────────────
    # If not set, uses creator's custom wallet or user default.
    custom_settlement_wallet = models.CharField(max_length=100, blank=True)
    custom_settlement_blockchain = models.CharField(max_length=10, blank=True, default="TRX")
    custom_settlement_currency = models.CharField(max_length=10, blank=True, default="USDT")

    # ── Access token behavior ─────────────────────────────────────────────
    token_expires_hours = models.PositiveIntegerField(default=0, help_text="0 = never")
    token_max_uses = models.PositiveIntegerField(default=1, help_text="1 = single use")

    # ── Success & branding ────────────────────────────────────────────────
    success_message = models.TextField(blank=True)
    success_redirect_url = models.URLField(blank=True)
    send_welcome_email = models.BooleanField(default=True)
    custom_email_template = models.TextField(blank=True)

    # ── Webhooks & external notifications ─────────────────────────────────
    webhook_url = models.URLField(blank=True)
    webhook_secret = models.CharField(max_length=200, blank=True)

    # ── Analytics ─────────────────────────────────────────────────────────
    view_count = models.PositiveIntegerField(default=0)
    conversion_count = models.PositiveIntegerField(default=0)
    revenue_usd = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))

    class Meta:
        db_table = "payable_assets"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["creator", "is_active"]),
            models.Index(fields=["pricing_type"]),
        ]

    def __str__(self):
        return f"{self.title} (${self.price_usd})"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            slug = base
            n = 1
            while PayableAsset.objects.filter(slug=slug).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def total_sales(self):
        return self.sales.filter(status=CreatorSale.Status.PAID).count()

    @property
    def is_sold_out(self):
        if self.max_sales is None:
            return False
        return self.total_sales >= self.max_sales

    def get_settlement_wallet(self):
        if self.custom_settlement_wallet:
            return self.custom_settlement_wallet
        return self.creator.get_payout_wallet()


class CreatorSale(TimeStampedModel):
    """
    A single sale of a PayableAsset. Linked to Payment and AccessGrant.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending Payment"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed (paid to creator)"
        REFUNDED = "refunded", "Refunded"
        FAILED = "failed", "Failed"

    asset = models.ForeignKey(PayableAsset, on_delete=models.CASCADE, related_name="sales")
    buyer_email = models.EmailField()
    buyer_name = models.CharField(max_length=120, blank=True)
    amount_usd = models.DecimalField(max_digits=12, decimal_places=2)
    commission_usd = models.DecimalField(max_digits=12, decimal_places=2)
    net_usd = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    access_token = models.CharField(max_length=255, blank=True)
    access_grant_id = models.UUIDField(null=True, blank=True, help_text="Reference to gating.AccessGrant")
    payment_id = models.UUIDField(null=True, blank=True, help_text="Reference to payments.Payment")
    payout_id = models.CharField(max_length=100, blank=True, help_text="PayRam payout ID")
    paid_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)  # IP, user agent, affiliate code

    class Meta:
        db_table = "creator_sales"
        indexes = [
            models.Index(fields=["asset", "status"]),
            models.Index(fields=["buyer_email"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return f"{self.asset.title} → {self.buyer_email} (${self.amount_usd})"

    def mark_paid(self, payout_id: str = None):
        self.status = self.Status.COMPLETED
        if payout_id:
            self.payout_id = payout_id
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "payout_id", "paid_at"])


class CreatorAffiliateProgram(models.Model):
    """
    Creators can offer affiliate programs to others.
    Affiliates earn a commission on sales they refer.
    """
    asset = models.OneToOneField(PayableAsset, on_delete=models.CASCADE, related_name="affiliate_program")
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=10.00)
    is_active = models.BooleanField(default=True)
    cookie_days = models.PositiveIntegerField(default=30)

    class Meta:
        db_table = "creator_affiliate_programs"

    def __str__(self):
        return f"Affiliate for {self.asset.title} ({self.commission_percent}%)"


class CreatorDiscountCode(models.Model):
    """
    Creators can generate discount codes for their assets.
    """
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percentage"
        FIXED = "fixed", "Fixed Amount"

    asset = models.ForeignKey(PayableAsset, on_delete=models.CASCADE, related_name="discount_codes")
    code = models.CharField(max_length=50, db_index=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    max_uses = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "creator_discount_codes"
        unique_together = [["asset", "code"]]

    def __str__(self):
        return f"{self.code} ({self.discount_value}{'%' if self.discount_type == 'percent' else '$'})"

    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        if now < self.valid_from:
            return False
        if self.max_uses > 0 and self.used_count >= self.max_uses:
            return False
        return True

    def apply(self, amount):
        if not self.is_valid():
            return amount
        if self.discount_type == self.DiscountType.PERCENT:
            discount = amount * (self.discount_value / 100)
        else:
            discount = min(self.discount_value, amount)
        return amount - discount