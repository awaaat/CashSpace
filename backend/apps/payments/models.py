"""
payments/models.py
==================
Multi‑chain, multi‑currency payment and webhook models for CashSpace.

PayRam Integration Reference:
    - Supported Chains: Bitcoin (BTC), Ethereum (ETH), Tron (TRX), Base (BASE), Polygon (POL)
    - Supported Tokens: BTC, ETH, USDT, USDC, TRX
    - Valid pairs: (BTC,BTC), (ETH,ETH|USDT|USDC), (TRX,TRX|USDT), (BASE,USDC), (POL,USDT|USDC)
    - Payment Methods: Card (via onramp), direct crypto (USDC, USDT, BTC, ETH)
    - Settlement: Always crypto, regardless of customer's payment method
    - Webhook events: OPEN, FILLED, PARTIALLY_FILLED, OVER_FILLED, CANCELLED

Flow (operator commission model):
  1. User initiates payment → Payment created (status=PENDING)
  2. PayRam session created → status=OPEN, payram_payment_url set
  3. User pays via PayRam checkout (card or crypto)
  4. PayRam webhook fires → status=FILLED
     → Full amount lands in YOUR cold wallet (in crypto, e.g., 100 USDT on TRX)
  5. Celery task calculates commission in USD:
        commission_usd    = amount_usd × COMMISSION_RATE (30%)
        payout_usd        = amount_usd × (1 − COMMISSION_RATE) (70%)
     Converts payout_usd to crypto using current rate → pays user in crypto
  6. payram_payout_id stored; payout_status updated via Celery polling/webhook

Merchant flow (NEW):
  - Payment.merchant links to the Merchant who owns the product being purchased.
  - Payment.customer_checkout links to the CustomerCheckout identity record.
  - When status hits FILLED, tasks.process_payout_after_payment fires the
    merchant's PostPaymentActions (Telegram invite, email delivery, etc.)
    in addition to the normal payout flow.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from apps.core.models import TimeStampedModel

DEFAULT_COMMISSION_RATE = Decimal("0.30")

def get_commission_rate() -> Decimal:
    rate = getattr(settings, "CASHSPACE_COMMISSION_RATE", DEFAULT_COMMISSION_RATE)
    return Decimal(str(rate))


class Blockchain(models.TextChoices):
    """Blockchain codes as required by PayRam's API."""
    BITCOIN = "BTC", "Bitcoin"
    ETHEREUM = "ETH", "Ethereum"
    TRON = "TRX", "Tron"
    BASE = "BASE", "Base"
    POLYGON = "POL", "Polygon"


class Currency(models.TextChoices):
    """Currency/token codes as required by PayRam's API."""
    BTC = "BTC", "Bitcoin"
    ETH = "ETH", "Ethereum"
    USDT = "USDT", "Tether USD"
    USDC = "USDC", "USD Coin"
    TRX = "TRX", "Tron"


# PayRam API validation: which currencies are valid per blockchain
# Source: PayRam TypeScript SDK docs — blockchainCode + currencyCode pairs
VALID_PAYRAM_PAIRS = {
    Blockchain.BITCOIN: [Currency.BTC],
    Blockchain.ETHEREUM: [Currency.ETH, Currency.USDT, Currency.USDC],
    Blockchain.TRON: [Currency.TRX, Currency.USDT],
    Blockchain.BASE: [Currency.USDC],
    Blockchain.POLYGON: [Currency.USDT, Currency.USDC],
}


class PaymentMethod(models.TextChoices):
    """
    How the customer paid on PayRam's checkout page.
    PayRam's onramp handles the conversion; we only care about the settlement.
    """
    CARD = "CARD", "Card (Visa/Mastercard via onramp)"
    CRYPTO_USDC = "CRYPTO_USDC", "Crypto - USDC"
    CRYPTO_USDT = "CRYPTO_USDT", "Crypto - USDT"
    CRYPTO_BTC = "CRYPTO_BTC", "Crypto - BTC"
    CRYPTO_ETH = "CRYPTO_ETH", "Crypto - ETH"


class Payment(TimeStampedModel):
    """
    Represents a single payment initiated by a user.

    Two modes:
      1. Direct buyer payment (existing flow) — user buys crypto for themselves.
         merchant = None, customer_checkout = None.

      2. Merchant checkout payment (new flow) — buyer purchases a merchant's product.
         merchant = the Merchant selling the product.
         customer_checkout = the CustomerCheckout identity record for this buyer.
         Payout goes to merchant's settlement wallet, not the buyer's wallet.

    The user pays in USD (amount_usd). CashSpace takes commission in USD.
    The payout is sent in CRYPTO (blockchain_code + currency_code)
    to destination_wallet.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"                     # Created, awaiting PayRam session
        OPEN = "OPEN", "Open"                              # PayRam session active
        FILLED = "FILLED", "Completed"                     # Fully paid
        PARTIALLY_FILLED = "PARTIALLY_FILLED", "Partially Filled"
        OVER_FILLED = "OVER_FILLED", "Over-Filled"         # Overpaid
        CANCELLED = "CANCELLED", "Cancelled"
        FAILED = "FAILED", "Failed"                        # API/communication error

    class PayoutStatus(models.TextChoices):
        NOT_INITIATED = "NOT_INITIATED", "Not Initiated"
        PENDING_APPROVAL = "pending-approval", "Pending Approval"
        APPROVED = "approved", "Approved"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    # ── Relations ─────────────────────────────────────────────────────────────
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payments",
        db_index=True,
        help_text="User who initiated this payment (buyer account, or anonymous guest via merchant checkout)",
    )

    # ── Merchant link (NEW) ───────────────────────────────────────────────────
    # Set when this payment was created via a merchant's checkout page.
    # Null for direct buyer-to-crypto purchases (legacy flow).
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        help_text="Merchant whose product is being purchased. Null for direct purchases.",
    )

    # ── Customer checkout identity (NEW) ──────────────────────────────────────
    # The buyer's identity captured at the merchant's checkout page.
    # One-to-one: each CustomerCheckout produces exactly one Payment.
    # Access via payment.customer_checkout (reverse of OneToOneField in CustomerCheckout).
    # We don't define the FK here — it's defined as a OneToOneField on CustomerCheckout
    # pointing back to Payment. Django creates payment.customer_checkout automatically.

    # ── Fiat amount (what user is charged in USD) ────────────────────────────
    amount_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Full amount the user is charged in USD (card or crypto checkout)",
    )

    # ── Payout crypto details (what recipient receives) ───────────────────────
    # For merchant payments: destination_wallet = merchant's settlement wallet.
    # For direct purchases: destination_wallet = buyer's wallet.
    blockchain_code = models.CharField(
        max_length=10,
        choices=Blockchain.choices,
        help_text="Blockchain to send payout on (BTC, ETH, TRX, BASE, POL)",
    )
    currency_code = models.CharField(
        max_length=10,
        choices=Currency.choices,
        help_text="Currency/token to send (BTC, ETH, USDT, USDC, TRX)",
    )
    destination_wallet = models.CharField(
        max_length=100,
        help_text="Wallet address receiving the payout (buyer wallet or merchant settlement wallet)",
    )

    # ── Exchange rate snapshot (critical audit trail) ────────────────────────
    exchange_rate_usd_to_crypto = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Rate used: 1 USD = X crypto (e.g., 1.00 for USDC, 0.000027 for BTC)",
    )
    payout_crypto_amount = models.DecimalField(
        max_digits=20,
        decimal_places=8,
        null=True,
        blank=True,
        help_text="Amount in crypto sent to recipient (payout_usd × exchange_rate)",
    )
    payout_usd_equivalent = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="USD equivalent of payout after commission deduction",
    )

    # ── Commission (operator revenue, kept in USD) ───────────────────────────
    # For merchant payments, commission_rate comes from merchant.get_effective_commission_rate().
    commission_rate = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        default=DEFAULT_COMMISSION_RATE,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        help_text="Commission rate applied (e.g., 0.3000 = 30%)",
    )
    commission_usd = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Commission amount kept by CashSpace (amount_usd × commission_rate)",
    )

    # ── How the customer paid (from PayRam webhook) ──────────────────────────
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        null=True,
        blank=True,
        help_text="Payment method the customer used on PayRam checkout",
    )
    payment_method_details = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional payment method metadata (card brand, last4, etc.)",
    )

    # ── PayRam payment session data ──────────────────────────────────────────
    payram_reference_id = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        help_text="PayRam reference_id returned when creating payment session",
    )
    payram_payment_url = models.URLField(
        max_length=500,
        blank=True,
        help_text="PayRam-hosted checkout URL — redirect user here",
    )

    # ── Payment status ───────────────────────────────────────────────────────
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
        help_text="Current status of the payment on PayRam",
    )
    payram_raw_status = models.CharField(
        max_length=30,
        blank=True,
        help_text="Raw paymentState string received from PayRam",
    )

    # ── PayRam payout data ───────────────────────────────────────────────────
    payram_payout_id = models.IntegerField(
        null=True,
        blank=True,
        db_index=True,
        help_text="PayRam payout ID from POST /api/v1/withdrawal/merchant",
    )
    payout_status = models.CharField(
        max_length=30,
        choices=PayoutStatus.choices,
        default=PayoutStatus.NOT_INITIATED,
        help_text="Current status of the outgoing payout to the recipient wallet",
    )
    payout_initiated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when create_payout() was called",
    )
    payout_completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when payout reached 'completed' status",
    )
    payout_error = models.TextField(
        blank=True,
        help_text="Error detail if payout failed",
    )

    # ── Webhook tracking ─────────────────────────────────────────────────────
    last_webhook_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Last time we received a webhook for this payment",
    )
    webhook_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of webhooks received for this payment",
    )

    # ── Error & notes ────────────────────────────────────────────────────────
    error_message = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        db_table = "payments"
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["payram_reference_id"]),
            models.Index(fields=["payram_payout_id"]),
            models.Index(fields=["payout_status"]),
            models.Index(fields=["blockchain_code", "currency_code"]),
            models.Index(fields=["status", "payout_status"]),
            # NEW: merchant payments index
            models.Index(fields=["merchant", "status"]),
        ]

    def __str__(self) -> str:
        merchant_tag = f" [merchant: {self.merchant.slug}]" if self.merchant_id else ""
        return (
            f"Payment {self.id} — {self.user.email} "
            f"— ${self.amount_usd} → {self.payout_crypto_amount} {self.currency_code} "
            f"on {self.blockchain_code} — {self.status}{merchant_tag}"
        )

    def save(self, *args, **kwargs):
        """Validate that blockchain_code and currency_code form a valid PayRam pair."""
        if self.blockchain_code and self.currency_code:
            valid_currencies = VALID_PAYRAM_PAIRS.get(self.blockchain_code, [])
            if self.currency_code not in valid_currencies:
                raise ValueError(
                    f"Invalid pair: {self.blockchain_code}/{self.currency_code}. "
                    f"Valid options: {[(bc, cur) for bc, currencies in VALID_PAYRAM_PAIRS.items() for cur in currencies]}"
                )
        super().save(*args, **kwargs)

    def calculate_commission(self) -> None:
        """
        Populate commission_usd and payout_usd_equivalent from amount_usd.

        For merchant payments, uses merchant.get_effective_commission_rate()
        if the rate hasn't been explicitly set on this payment yet.

        Does NOT save — caller must call save() afterward.
        """
        if self.commission_rate == DEFAULT_COMMISSION_RATE and self.merchant_id:
            # Use merchant-specific rate if configured
            self.commission_rate = self.merchant.get_effective_commission_rate()

        rate = self.commission_rate or get_commission_rate()
        self.commission_rate = rate
        self.commission_usd = (self.amount_usd * rate).quantize(Decimal("0.01"))
        self.payout_usd_equivalent = (
            self.amount_usd - self.commission_usd
        ).quantize(Decimal("0.01"))

    def set_crypto_payout_amount(self, exchange_rate: Decimal) -> None:
        """
        Calculate payout_crypto_amount from payout_usd_equivalent and exchange_rate.
        exchange_rate: 1 USD = X crypto (1.0 for stablecoins, 0.000027 for BTC).
        """
        if self.payout_usd_equivalent is None:
            self.calculate_commission()
        self.exchange_rate_usd_to_crypto = exchange_rate
        self.payout_crypto_amount = (self.payout_usd_equivalent * exchange_rate).quantize(
            Decimal("0.00000001")
        )

    @property
    def is_merchant_payment(self) -> bool:
        """True when this payment is for a merchant product (not a direct purchase)."""
        return self.merchant_id is not None

    @property
    def is_terminal(self) -> bool:
        """True when payment is in a final state and no further PayRam updates expected."""
        return self.status in (
            self.Status.FILLED,
            self.Status.CANCELLED,
            self.Status.FAILED,
            self.Status.OVER_FILLED,
        )

    @property
    def payout_is_terminal(self) -> bool:
        """True when the payout has reached a final state."""
        return self.payout_status in (
            self.PayoutStatus.COMPLETED,
            self.PayoutStatus.FAILED,
        )

    @property
    def needs_payout(self) -> bool:
        """
        True when payment is FILLED, payout not initiated, and wallet address exists.
        Primary guard in the payout task.
        """
        return (
            self.status == self.Status.FILLED
            and self.payout_status == self.PayoutStatus.NOT_INITIATED
            and bool(self.destination_wallet)
            and self.payout_crypto_amount is not None
        )

    @property
    def needs_merchant_automation(self) -> bool:
        """
        True when this is a merchant payment that has been FILLED but
        post-payment automation hasn't fired yet.
        """
        if not self.is_merchant_payment:
            return False
        if self.status != self.Status.FILLED:
            return False
        try:
            return not self.customer_checkout.automation_triggered
        except Exception:
            return False

    @property
    def needs_manual_review(self) -> bool:
        """Flag for payments requiring admin attention (overpayment, payout failed)."""
        return (
            self.status == self.Status.OVER_FILLED
            or (self.payout_status == self.PayoutStatus.FAILED and not self.payout_is_terminal)
        )


class UserCryptoWallet(models.Model):
    """
    Stores a user's saved payout addresses for different blockchains/tokens.
    Each user can have multiple wallets (e.g., USDT on TRX, USDC on Base, BTC on Bitcoin).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="crypto_wallets",
        help_text="User who owns this wallet address",
    )
    blockchain_code = models.CharField(
        max_length=10,
        choices=Blockchain.choices,
        help_text="Blockchain this wallet belongs to",
    )
    currency_code = models.CharField(
        max_length=10,
        choices=Currency.choices,
        help_text="Currency/token this wallet receives",
    )
    wallet_address = models.CharField(
        max_length=100,
        help_text="User's wallet address (validate based on blockchain_code)",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this wallet can receive payouts",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="If true, this is the preferred wallet for this blockchain+currency",
    )
    label = models.CharField(
        max_length=100,
        blank=True,
        help_text="User-friendly name (e.g., 'My TRX USDT wallet')",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_crypto_wallets"
        verbose_name = "User Crypto Wallet"
        verbose_name_plural = "User Crypto Wallets"
        ordering = ["user", "blockchain_code", "currency_code"]
        unique_together = [
            ["user", "blockchain_code", "currency_code", "wallet_address"],
            ["user", "blockchain_code", "currency_code", "is_default"],
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "blockchain_code", "currency_code"],
                condition=models.Q(is_default=True),
                name="unique_default_per_user_per_chain_token",
            )
        ]

    def __str__(self) -> str:
        return (
            f"{self.user.email} — {self.currency_code} on {self.blockchain_code}: "
            f"{self.wallet_address[:12]}...{' (default)' if self.is_default else ''}"
        )


class WebhookEvent(TimeStampedModel):
    """
    Raw log of every webhook received from PayRam.
    Kept for audit, replay, and debugging purposes.
    """

    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="webhook_events",
        help_text="Related payment if successfully matched",
    )
    payram_reference_id = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        help_text="PayRam reference_id from the webhook",
    )
    event_type = models.CharField(
        max_length=100,
        blank=True,
        help_text="Event type: OPEN, FILLED, PARTIALLY_FILLED, OVER_FILLED, CANCELLED",
    )
    payload = models.JSONField(
        default=dict,
        help_text="Complete raw webhook payload from PayRam",
    )
    signature_valid = models.BooleanField(
        default=False,
        help_text="Whether the API-Key header matched our secret",
    )
    processed = models.BooleanField(
        default=False,
        help_text="Whether this event was successfully processed",
    )
    error = models.TextField(
        blank=True,
        help_text="Processing error if any",
    )

    class Meta:
        db_table = "webhook_events"
        verbose_name = "Webhook Event"
        verbose_name_plural = "Webhook Events"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["payram_reference_id", "event_type"]),
            models.Index(fields=["processed", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Webhook {self.event_type} — ref={self.payram_reference_id} — valid={self.signature_valid}"