"""
payments/tasks.py
=================
Celery tasks for the payments app.

Task inventory:
  process_payout_after_payment   — triggered when a payment hits FILLED;
                                   calculates 30% commission and calls
                                   PayRam's payout API for the remaining 70%.
  poll_payout_status             — polls PayRam for payout status until terminal.
  poll_open_payments             — periodic task: re-checks any non-terminal
                                   payments that haven't received a webhook.
  send_payment_confirmation_email — sends receipt email to the user.

Commission model reminder:
  amount_usd        → full amount charged to user's card
  commission_usd    = amount_usd × 0.30  (kept by CashSpace)
  payout_amount_usd = amount_usd × 0.70  (sent to user's wallet in USD equivalent)

[UPDATED] Multi‑chain / multi‑currency support:
  - The payout is sent in the user's chosen cryptocurrency (e.g., USDT on TRX)
  - Exchange rate is fetched to convert payout_usd_equivalent → payout_crypto_amount
  - blockchain_code and currency_code are passed to PayRam's create_payout()
  - Email includes the specific crypto and blockchain
"""

import logging
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from .payram_client import PayRamError, payram

logger = logging.getLogger("apps.payments")

# ── Constants ─────────────────────────────────────────────────────────────────

# How many times to retry a failed payout before giving up
PAYOUT_MAX_RETRIES = 5
PAYOUT_RETRY_BACKOFF = 60  # seconds between retries (Celery countdown)

# How many times to poll payout status before giving up
PAYOUT_POLL_MAX_RETRIES = 20
PAYOUT_POLL_INTERVAL = 30  # seconds


# ── Helper: fetch current exchange rate (USD → crypto) ────────────────────────

def get_exchange_rate(blockchain_code: str, currency_code: str) -> Decimal:
    """
    Fetch the current exchange rate from PayRam's ticker.
    Returns Decimal: 1 USD = X crypto.

    For stablecoins (USDC, USDT) on any chain, returns Decimal('1.00').
    For BTC/ETH/TRX, calculates from ticker price.
    """
    # Stablecoins are always 1:1 with USD
    if currency_code in ("USDC", "USDT"):
        return Decimal("1.00")

    # For non‑stablecoins, fetch from PayRam ticker
    try:
        ticker = payram.get_ticker()
        chain_data = ticker.get(blockchain_code, {})
        token_data = chain_data.get(currency_code, {})
        price_usd = token_data.get("priceInUSD")
        if price_usd:
            # priceInUSD is the price of 1 unit of crypto in USD.
            # Exchange rate (USD → crypto) = 1 / price_usd
            return Decimal("1.00") / Decimal(str(price_usd))
    except Exception as e:
        logger.warning("Failed to fetch exchange rate from PayRam: %s", e)

    # Fallback – should never happen in production; raise error
    raise ValueError(f"Cannot determine exchange rate for {currency_code} on {blockchain_code}")


# ── Payout task (multi‑chain upgrade) ─────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=PAYOUT_MAX_RETRIES,
    default_retry_delay=PAYOUT_RETRY_BACKOFF,
    name="payments.process_payout_after_payment",
)
def process_payout_after_payment(self, payment_id: str) -> None:
    """
    Called automatically when a payment reaches FILLED status.

    Steps:
      1. Re-fetch payment to guard against race conditions (webhook + poll
         both triggering the same task).
      2. Check payment.needs_payout (idempotency guard).
      3. Calculate commission and payout amounts.
      4. [UPDATED] Fetch exchange rate for the user's chosen blockchain/currency.
      5. [UPDATED] Convert payout_usd_equivalent → payout_crypto_amount.
      6. [UPDATED] Call PayRam POST /api/v1/withdrawal/merchant with blockchain_code,
         currency_code, and crypto amount (not USD).
      7. Persist payout ID and status on the Payment record.
      8. Schedule poll_payout_status to track the on-chain delivery.
    """
    # Import here to avoid circular imports at module load time
    from .models import Payment

    try:
        payment = Payment.objects.select_related("user").get(id=payment_id)
    except Payment.DoesNotExist:
        logger.error(
            "process_payout_after_payment: Payment %s not found", payment_id
        )
        return

    # ── Idempotency guard ─────────────────────────────────────────────────────
    # If two webhooks or a webhook + a status poll both fire at the same
    # time, the second task will see payout_status != NOT_INITIATED and exit.
    if not payment.needs_payout:
        logger.info(
            "Payout skipped (already initiated or payment not FILLED) "
            "| payment_id=%s | status=%s | payout_status=%s",
            payment_id,
            payment.status,
            payment.payout_status,
        )
        return

    # ── Calculate amounts ─────────────────────────────────────────────────────
    payment.calculate_commission()

    logger.info(
        "Initiating payout | payment_id=%s | charged=$%.2f "
        "| commission=$%.2f (%.0f%%) | payout_usd=$%.2f | wallet=%s",
        payment_id,
        payment.amount_usd,
        payment.commission_usd,
        payment.commission_rate * 100,
        payment.payout_usd_equivalent,
        payment.destination_wallet,
    )

    # [NEW] Fetch exchange rate and compute crypto payout amount
    try:
        exchange_rate = get_exchange_rate(payment.blockchain_code, payment.currency_code)
    except Exception as e:
        logger.error("Cannot get exchange rate for payment %s: %s", payment_id, e)
        payment.payout_status = Payment.PayoutStatus.FAILED
        payment.payout_error = f"Exchange rate fetch failed: {e}"
        payment.save(update_fields=["payout_status", "payout_error"])
        _alert_payout_failure(payment_id, str(e))
        return

    payment.set_crypto_payout_amount(exchange_rate)
    # Now payment.payout_crypto_amount is set (e.g., 70.0 USDT)

    logger.info(
        "Exchange rate applied | payment_id=%s | 1 USD = %f %s | payout_crypto=%f %s",
        payment_id,
        exchange_rate,
        payment.currency_code,
        payment.payout_crypto_amount,
        payment.currency_code,
    )

    # ── Mark as in-progress before the API call ───────────────────────────────
    payment.payout_status = Payment.PayoutStatus.PENDING_APPROVAL
    payment.payout_initiated_at = timezone.now()
    payment.save(
        update_fields=[
            "commission_rate",
            "commission_usd",
            "payout_usd_equivalent",
            "exchange_rate_usd_to_crypto",
            "payout_crypto_amount",
            "payout_status",
            "payout_initiated_at",
        ]
    )

    # ── Call PayRam Payout API (UPDATED: multi‑chain, crypto amount) ──────────
    try:
        result = payram.create_payout(
            email=payment.user.email,                     # changed from customer_email
            customer_id=str(payment.user.id),             # renamed from customer_id
            to_address=payment.destination_wallet,
            amount=payment.payout_crypto_amount,          # was amount_usd (float), now crypto Decimal
            blockchain_code=payment.blockchain_code,      # was "BTC"
            currency_code=payment.currency_code,          # was "BTC"
        )
    except PayRamError as exc:
        logger.error(
            "PayRam payout API error | payment_id=%s | error=%s", payment_id, exc
        )
        # NOTE: keep original behavior – reset to NOT_INITIATED so retry can run
        payment.payout_status = Payment.PayoutStatus.NOT_INITIATED
        payment.payout_error = str(exc)
        payment.save(update_fields=["payout_status", "payout_error"])

        # Retry with exponential backoff (Celery will raise Retry internally)
        try:
            raise self.retry(exc=exc, countdown=PAYOUT_RETRY_BACKOFF * (2 ** self.request.retries))
        except self.MaxRetriesExceededError:
            logger.critical(
                "Payout permanently failed after %d retries | payment_id=%s",
                PAYOUT_MAX_RETRIES,
                payment_id,
            )
            payment.payout_status = Payment.PayoutStatus.FAILED
            payment.payout_error = (
                f"Max retries ({PAYOUT_MAX_RETRIES}) exceeded. Last error: {exc}"
            )
            payment.save(update_fields=["payout_status", "payout_error"])
            # Alert the team — this needs manual intervention
            _alert_payout_failure(payment_id, str(exc))
        return

    # ── Persist payout result ─────────────────────────────────────────────────
    payout_id = result.get("id")
    raw_status = result.get("status", "pending-approval")

    # Map PayRam status string → our PayoutStatus choices
    STATUS_MAP = {
        "pending-approval": Payment.PayoutStatus.PENDING_APPROVAL,
        "approved": Payment.PayoutStatus.APPROVED,
        "completed": Payment.PayoutStatus.COMPLETED,
        "failed": Payment.PayoutStatus.FAILED,
    }
    payout_status = STATUS_MAP.get(raw_status, Payment.PayoutStatus.PENDING_APPROVAL)

    payment.payram_payout_id = payout_id
    payment.payout_status = payout_status
    payment.save(update_fields=["payram_payout_id", "payout_status"])

    logger.info(
        "Payout created | payment_id=%s | payout_id=%s | status=%s | blockchain=%s | currency=%s",
        payment_id,
        payout_id,
        raw_status,
        payment.blockchain_code,
        payment.currency_code,
    )

    # ── Schedule status polling if not already done ───────────────────────────
    if payout_status not in (Payment.PayoutStatus.COMPLETED, Payment.PayoutStatus.FAILED):
        poll_payout_status.apply_async(
            args=[payment_id],
            countdown=PAYOUT_POLL_INTERVAL,
        )

    # ── Send confirmation email (updated to include crypto details) ───────────
    send_payment_confirmation_email.delay(payment_id)


# ── Payout status polling (works with multi‑chain, no changes needed) ─────────

@shared_task(
    bind=True,
    max_retries=PAYOUT_POLL_MAX_RETRIES,
    default_retry_delay=PAYOUT_POLL_INTERVAL,
    name="payments.poll_payout_status",
)
def poll_payout_status(self, payment_id: str) -> None:
    """
    Polls PayRam GET /api/v1/withdrawal/merchant/{id} until the payout
    reaches a terminal state (completed or failed).

    Schedules itself again via Celery retry until terminal or max retries hit.
    """
    from .models import Payment

    try:
        payment = Payment.objects.get(id=payment_id)
    except Payment.DoesNotExist:
        logger.error("poll_payout_status: Payment %s not found", payment_id)
        return

    if payment.payout_is_terminal:
        logger.debug(
            "Payout already terminal | payment_id=%s | payout_status=%s",
            payment_id,
            payment.payout_status,
        )
        return

    if not payment.payram_payout_id:
        logger.warning(
            "poll_payout_status: no payout_id on payment %s", payment_id
        )
        return

    try:
        result = payram.get_payout_by_id(payment.payram_payout_id)  # updated method name
    except PayRamError as exc:
        logger.warning(
            "Payout status poll failed | payment_id=%s | error=%s",
            payment_id,
            exc,
        )
        # Retry silently — transient network issue
        raise self.retry(exc=exc)

    raw_status = result.get("status", "")
    STATUS_MAP = {
        "pending-approval": Payment.PayoutStatus.PENDING_APPROVAL,
        "approved": Payment.PayoutStatus.APPROVED,
        "completed": Payment.PayoutStatus.COMPLETED,
        "failed": Payment.PayoutStatus.FAILED,
    }
    new_payout_status = STATUS_MAP.get(raw_status, payment.payout_status)

    if new_payout_status != payment.payout_status:
        update_fields = ["payout_status"]
        payment.payout_status = new_payout_status

        if new_payout_status == Payment.PayoutStatus.COMPLETED:
            payment.payout_completed_at = timezone.now()
            update_fields.append("payout_completed_at")
            logger.info(
                "Payout COMPLETED | payment_id=%s | payout_id=%s | wallet=%s | tx_hash=%s",
                payment_id,
                payment.payram_payout_id,
                payment.destination_wallet,
                result.get("transferHash", "unknown"),
            )

        if new_payout_status == Payment.PayoutStatus.FAILED:
            payment.payout_error = result.get("error", "PayRam reported payout failed")
            update_fields.append("payout_error")
            logger.error(
                "Payout FAILED | payment_id=%s | payout_id=%s | error=%s",
                payment_id,
                payment.payram_payout_id,
                payment.payout_error,
            )
            _alert_payout_failure(payment_id, payment.payout_error)

        payment.save(update_fields=update_fields)

    # Re-schedule if not yet terminal
    if not payment.payout_is_terminal:
        raise self.retry(countdown=PAYOUT_POLL_INTERVAL)


# ── Periodic payment status sweep (unchanged logic) ───────────────────────────

@shared_task(name="payments.poll_open_payments")
def poll_open_payments() -> None:
    """
    Periodic task (run every 5 minutes via Celery Beat) that re-checks any
    non-terminal payments.  This catches cases where a webhook was missed
    (network blip, PayRam retry window expired, etc.).

    Add to your CELERY_BEAT_SCHEDULE in settings.py:
        "poll-open-payments": {
            "task": "payments.poll_open_payments",
            "schedule": 300,  # every 5 minutes
        }
    """
    from .models import Payment

    # Only poll payments that are not yet terminal and have a reference ID
    open_payments = Payment.objects.filter(
        status__in=[Payment.Status.OPEN, Payment.Status.PARTIALLY_FILLED],
        payram_reference_id__isnull=False,
    ).exclude(payram_reference_id="")

    count = open_payments.count()
    if count == 0:
        return

    logger.info("Polling %d open payment(s) for status updates", count)

    STATE_MAP = {
        "OPEN": Payment.Status.OPEN,
        "FILLED": Payment.Status.FILLED,
        "PARTIALLY_FILLED": Payment.Status.PARTIALLY_FILLED,
        "OVER_FILLED": Payment.Status.OVER_FILLED,
        "CANCELLED": Payment.Status.CANCELLED,
    }

    for payment in open_payments:
        try:
            result = payram.get_payment_request(payment.payram_reference_id)  # updated method name
            payram_state = result.get("paymentState", "")
            new_status = STATE_MAP.get(payram_state, payment.status)

            if new_status != payment.status:
                payment.status = new_status
                payment.payram_raw_status = payram_state
                payment.save(update_fields=["status", "payram_raw_status", "updated_at"])
                logger.info(
                    "poll_open_payments: payment %s → %s", payment.id, new_status
                )

                if new_status == Payment.Status.FILLED and payment.needs_payout:
                    process_payout_after_payment.delay(str(payment.id))

        except PayRamError as exc:
            logger.warning(
                "poll_open_payments: status check failed for payment %s: %s",
                payment.id,
                exc,
            )


# ── Email confirmation (updated to include crypto and blockchain details) ─────

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="payments.send_payment_confirmation_email",
)
def send_payment_confirmation_email(self, payment_id: str) -> None:
    """
    Sends a payment receipt email to the user once their payment is FILLED
    and the payout has been initiated.

    Email contains:
      - Amount charged
      - Commission taken (%)
      - Amount of crypto being sent (with currency and blockchain)
      - Destination wallet address
      - PayRam payout ID (for user reference)
    """
    from .models import Payment
    from django.core.mail import send_mail
    from django.conf import settings as django_settings

    try:
        payment = Payment.objects.select_related("user").get(id=payment_id)
    except Payment.DoesNotExist:
        logger.error(
            "send_payment_confirmation_email: Payment %s not found", payment_id
        )
        return

    user = payment.user
    subject = f"CashSpace — Your {payment.currency_code} purchase is on its way"

    payout_display = (
        f"{payment.payout_crypto_amount:.8f} {payment.currency_code}"
        if payment.payout_crypto_amount
        else "calculating..."
    )
    commission_display = (
        f"${payment.commission_usd:.2f} ({int(payment.commission_rate * 100)}%)"
        if payment.commission_usd
        else "N/A"
    )

    message = (
        f"Hi {user.first_name or user.email},\n\n"
        f"Your crypto purchase on CashSpace has been processed.\n\n"
        f"  Amount charged:        ${payment.amount_usd:.2f}\n"
        f"  Service fee:           {commission_display}\n"
        f"  Crypto being sent:     {payout_display}\n"
        f"  Blockchain:            {payment.blockchain_code}\n"
        f"  Destination wallet:    {payment.destination_wallet}\n"
        f"  Payout reference:      {payment.payram_payout_id or 'pending'}\n\n"
        f"Your {payment.currency_code} will arrive in your wallet within a few minutes "
        f"once the transaction is confirmed on the {payment.blockchain_code} network.\n\n"
        f"— The CashSpace Team\n"
    )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(
            "Payment confirmation email sent | payment_id=%s | email=%s",
            payment_id,
            user.email,
        )
    except Exception as exc:
        logger.error(
            "Failed to send confirmation email | payment_id=%s | error=%s",
            payment_id,
            exc,
        )
        raise self.retry(exc=exc)


# ── Internal helpers (unchanged) ──────────────────────────────────────────────

def _alert_payout_failure(payment_id: str, error: str) -> None:
    """
    Send an internal alert when a payout fails permanently.
    Replace the email body with your preferred alerting mechanism
    (Slack, PagerDuty, Sentry, etc.).
    """
    from django.core.mail import send_mail
    from django.conf import settings as django_settings

    admins = getattr(django_settings, "ADMINS", [])
    if not admins:
        logger.warning(
            "_alert_payout_failure: no ADMINS configured in settings.py"
        )
        return

    admin_emails = [email for _, email in admins]

    try:
        send_mail(
            subject=f"[CashSpace] URGENT: Payout failed for payment {payment_id}",
            message=(
                f"Payment ID: {payment_id}\n"
                f"Error: {error}\n\n"
                f"Manual intervention required. Log into the CashSpace admin "
                f"panel and the PayRam dashboard to resolve."
            ),
            from_email=django_settings.DEFAULT_FROM_EMAIL,
            recipient_list=admin_emails,
            fail_silently=True,
        )
    except Exception as exc:
        logger.error("Failed to send payout failure alert: %s", exc)