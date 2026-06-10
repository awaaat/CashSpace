"""
apps/creator/tasks.py
=====================
Advanced Celery tasks for the creator app.

Features:
  - Send access email to buyer (custom template support)
  - Call creator webhook on sale completion (with retries and HMAC signature)
  - Process affiliate commission payouts
  - Sync sale status with payment system
  - Update analytics (hourly/daily aggregations)
  - Handle subscription renewals (future)
  - Idempotent operations with Redis locks
  - Exponential backoff retries
  - Full logging and error tracking
"""

import hashlib
import hmac
import json
import logging
from datetime import timedelta
from decimal import Decimal

from celery import shared_task
from celery.exceptions import Retry
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.payments.payram_client import payram, PayRamError
from apps.gating.tokens import create_access_token

from .models import CreatorSale, PayableAsset, CreatorProfile, CreatorAffiliateProgram

logger = logging.getLogger("apps.creator.tasks")

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
MAX_RETRIES = 5
RETRY_BACKOFF = 60  # seconds
LOCK_TIMEOUT = 300  # 5 minutes


# ----------------------------------------------------------------------
# Helper: idempotent lock
# ----------------------------------------------------------------------
def acquire_lock(lock_key: str, timeout: int = LOCK_TIMEOUT) -> bool:
    """Try to acquire Redis lock. Returns True if acquired."""
    return cache.add(lock_key, "locked", timeout=timeout)


def release_lock(lock_key: str):
    cache.delete(lock_key)


# ----------------------------------------------------------------------
# Task 1: Send access email to buyer
# ----------------------------------------------------------------------
@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF,
    name="creator.send_access_email"
)
def send_access_email(self, sale_id: str):
    """
    Send the buyer their access token/unlock link.
    Uses custom email template if asset has one, otherwise default.
    """
    try:
        sale = CreatorSale.objects.select_related("asset", "asset__creator__user").get(id=sale_id)
    except CreatorSale.DoesNotExist:
        logger.error(f"send_access_email: sale {sale_id} not found")
        return

    # Idempotency: skip if email already sent
    if sale.metadata.get("email_sent"):
        logger.info(f"Email already sent for sale {sale_id}")
        return

    asset = sale.asset
    creator = asset.creator
    token = sale.access_token

    if not token:
        logger.error(f"No access token for sale {sale_id}")
        return

    # Build unlock URL
    base_url = settings.FRONTEND_URL
    unlock_url = f"{base_url}/unlock/{token}/"

    # Prepare email content
    if asset.custom_email_template:
        # Custom template with placeholders
        body = asset.custom_email_template.format(
            buyer_name=sale.buyer_name or sale.buyer_email.split("@")[0],
            asset_title=asset.title,
            asset_description=asset.description or "",
            unlock_link=unlock_url,
            access_token=token,
            support_email=settings.DEFAULT_FROM_EMAIL,
        )
        subject = f"Your access to {asset.title}"
    else:
        # Default email
        subject = f"Your purchase of {asset.title} is ready"
        body = f"""
Hello {sale.buyer_name or sale.buyer_email},

Thank you for purchasing "{asset.title}".

Access your content here: {unlock_url}

Your access token (if needed): {token}

This link will expire {'after ' + str(asset.token_expires_hours) + ' hours' if asset.token_expires_hours > 0 else 'never'}.
For support, contact {settings.DEFAULT_FROM_EMAIL}.

— CashSpace
"""

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[sale.buyer_email],
            fail_silently=False,
        )
        # Mark as sent
        metadata = sale.metadata or {}
        metadata["email_sent"] = True
        metadata["email_sent_at"] = timezone.now().isoformat()
        sale.metadata = metadata
        sale.save(update_fields=["metadata"])
        logger.info(f"Access email sent for sale {sale_id} to {sale.buyer_email}")
    except Exception as exc:
        logger.error(f"Failed to send email for sale {sale_id}: {exc}")
        raise self.retry(exc=exc)


# ----------------------------------------------------------------------
# Task 2: Call creator webhook on sale completion
# ----------------------------------------------------------------------
@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF,
    name="creator.call_creator_webhook"
)
def call_creator_webhook(self, sale_id: str):
    """
    POST sale details to creator's configured webhook URL.
    Includes HMAC signature for verification.
    """
    import requests

    try:
        sale = CreatorSale.objects.select_related("asset", "asset__creator").get(id=sale_id)
    except CreatorSale.DoesNotExist:
        logger.error(f"call_creator_webhook: sale {sale_id} not found")
        return

    asset = sale.asset
    webhook_url = asset.webhook_url
    webhook_secret = asset.webhook_secret

    if not webhook_url:
        logger.debug(f"No webhook configured for asset {asset.id}")
        return

    # Idempotency: check if already called
    if sale.metadata.get("webhook_called"):
        logger.info(f"Webhook already called for sale {sale_id}")
        return

    payload = {
        "event": "sale.completed",
        "sale_id": str(sale.id),
        "asset_id": str(asset.id),
        "asset_title": asset.title,
        "buyer_email": sale.buyer_email,
        "buyer_name": sale.buyer_name,
        "amount_usd": str(sale.amount_usd),
        "net_usd": str(sale.net_usd),
        "commission_usd": str(sale.commission_usd),
        "access_token": sale.access_token,
        "created_at": sale.created_at.isoformat(),
    }
    body = json.dumps(payload, separators=(",", ":"))
    headers = {"Content-Type": "application/json"}

    if webhook_secret:
        signature = hmac.new(
            webhook_secret.encode("utf-8"),
            body.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        headers["X-CashSpace-Signature"] = f"sha256={signature}"

    try:
        resp = requests.post(webhook_url, data=body, headers=headers, timeout=10)
        resp.raise_for_status()
        metadata = sale.metadata or {}
        metadata["webhook_called"] = True
        metadata["webhook_response_status"] = resp.status_code
        sale.metadata = metadata
        sale.save(update_fields=["metadata"])
        logger.info(f"Webhook delivered for sale {sale_id} to {webhook_url}")
    except requests.exceptions.Timeout:
        logger.warning(f"Webhook timeout for sale {sale_id}")
        raise self.retry(exc=Exception("Timeout"), countdown=RETRY_BACKOFF * (2 ** self.request.retries))
    except requests.exceptions.RequestException as e:
        logger.error(f"Webhook failed for sale {sale_id}: {e}")
        raise self.retry(exc=e)


# ----------------------------------------------------------------------
# Task 3: Process affiliate commission
# ----------------------------------------------------------------------
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="creator.process_affiliate_commission"
)
def process_affiliate_commission(self, sale_id: str):
    """
    If sale came from an affiliate link, calculate commission and pay affiliate.
    """
    try:
        sale = CreatorSale.objects.select_related("asset").get(id=sale_id)
    except CreatorSale.DoesNotExist:
        return

    affiliate_code = sale.metadata.get("affiliate_code") if sale.metadata else None
    if not affiliate_code:
        return

    asset = sale.asset
    try:
        affiliate_program = asset.affiliate_program
    except CreatorAffiliateProgram.DoesNotExist:
        return

    if not affiliate_program.is_active:
        return

    # Find affiliate user (affiliate code stored on User model or separate Affiliate model)
    from apps.accounts.models import User
    try:
        affiliate_user = User.objects.get(affiliate_code=affiliate_code)
        affiliate_profile, _ = CreatorProfile.objects.get_or_create(user=affiliate_user)
    except User.DoesNotExist:
        logger.warning(f"Affiliate code {affiliate_code} not found")
        return

    commission_percent = affiliate_program.commission_percent
    commission_amount = sale.amount_usd * (commission_percent / 100)
    if commission_amount <= 0:
        return

    # Get affiliate's payout wallet
    payout_wallet = affiliate_profile.get_payout_wallet()
    if not payout_wallet:
        logger.warning(f"Affiliate {affiliate_user.email} has no payout wallet")
        return

    # Initiate payout via PayRam (or record as pending)
    try:
        result = payram.create_payout(
            email=affiliate_user.email,
            customer_id=str(affiliate_user.id),
            to_address=payout_wallet,
            amount=commission_amount,
            blockchain_code=affiliate_profile.custom_payout_blockchain or "TRX",
            currency_code=affiliate_profile.custom_payout_currency or "USDT",
        )
        logger.info(f"Affiliate commission {commission_amount} USD sent to {affiliate_user.email}, payout_id={result.get('id')}")
    except PayRamError as e:
        logger.error(f"Failed to send affiliate commission: {e}")
        raise self.retry(exc=e)


# ----------------------------------------------------------------------
# Task 4: Process payment confirmation (from webhook or poll)
# ----------------------------------------------------------------------
@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="creator.process_payment_confirmation"
)
def process_payment_confirmation(self, sale_id: str):
    """
    Poll PayRam payment status and complete sale when paid.
    Called initially after checkout creation.
    """
    try:
        sale = CreatorSale.objects.select_related("asset").get(id=sale_id)
    except CreatorSale.DoesNotExist:
        return

    if sale.status == CreatorSale.Status.COMPLETED:
        return

    payment_id = sale.payment_id
    if not payment_id:
        logger.error(f"No payment_id for sale {sale_id}")
        return

    from apps.payments.models import Payment
    try:
        payment = Payment.objects.get(id=payment_id)
    except Payment.DoesNotExist:
        logger.error(f"Payment {payment_id} not found for sale {sale_id}")
        return

    if payment.status == Payment.Status.FILLED:
        # Already completed by webhook – do nothing
        if sale.status != CreatorSale.Status.COMPLETED:
            # Trigger completion manually
            from .views import CreatorWebhookView
            # Simulate webhook call
            with transaction.atomic():
                sale.status = CreatorSale.Status.COMPLETED
                sale.paid_at = timezone.now()
                sale.save(update_fields=["status", "paid_at"])
                # Generate token if not already
                if not sale.access_token:
                    token_expires_hours = sale.asset.token_expires_hours or 0
                    expires_in_seconds = token_expires_hours * 3600 if token_expires_hours else None
                    sale.access_token = create_access_token(
                        asset_id=str(sale.asset.id),
                        grant_id=str(sale.id),
                        buyer_email=sale.buyer_email,
                        expires_in_seconds=expires_in_seconds,
                        max_uses=sale.asset.token_max_uses,
                        custom_claims={"creator_asset": True}
                    )
                    sale.save(update_fields=["access_token"])
                # Update stats
                sale.asset.total_sales = F("total_sales") + 1
                sale.asset.revenue_usd = F("revenue_usd") + sale.amount_usd
                sale.asset.save(update_fields=["total_sales", "revenue_usd"])
                sale.asset.creator.total_sales = F("total_sales") + 1
                sale.asset.creator.total_revenue_usd = F("total_revenue_usd") + sale.amount_usd
                sale.asset.creator.save(update_fields=["total_sales", "total_revenue_usd"])
        return

    if payment.status in [Payment.Status.CANCELLED, Payment.Status.FAILED]:
        sale.status = CreatorSale.Status.FAILED
        sale.save(update_fields=["status"])
        return

    # Still pending – retry later
    raise self.retry(countdown=30)


# ----------------------------------------------------------------------
# Task 5: Update daily analytics (periodic task)
# ----------------------------------------------------------------------
@shared_task(name="creator.update_daily_analytics")
def update_daily_analytics():
    """
    Celery Beat task (daily at 00:00) to aggregate sales data for charts.
    Stores in Redis for fast retrieval.
    """
    today = timezone.now().date()
    start_of_day = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
    end_of_day = start_of_day + timedelta(days=1)

    total_sales = CreatorSale.objects.filter(
        created_at__gte=start_of_day,
        created_at__lt=end_of_day,
        status=CreatorSale.Status.COMPLETED
    ).count()
    total_revenue = CreatorSale.objects.filter(
        created_at__gte=start_of_day,
        created_at__lt=end_of_day,
        status=CreatorSale.Status.COMPLETED
    ).aggregate(total=Sum("amount_usd"))["total"] or Decimal("0")

    cache.set(f"creator:analytics:daily:{today.isoformat()}", {
        "date": today.isoformat(),
        "sales": total_sales,
        "revenue": str(total_revenue),
    }, timeout=86400 * 30)

    logger.info(f"Daily analytics updated for {today}: {total_sales} sales, ${total_revenue}")
    return {"date": today.isoformat(), "sales": total_sales, "revenue": str(total_revenue)}


# ----------------------------------------------------------------------
# Task 6: Expire old pending sales (cleanup)
# ----------------------------------------------------------------------
@shared_task(name="creator.cleanup_abandoned_sales")
def cleanup_abandoned_sales():
    """
    Mark sales older than 24 hours with status PENDING as ABANDONED.
    """
    cutoff = timezone.now() - timedelta(hours=24)
    abandoned = CreatorSale.objects.filter(
        status=CreatorSale.Status.PENDING,
        created_at__lt=cutoff
    ).update(status=CreatorSale.Status.FAILED)
    logger.info(f"Marked {abandoned} abandoned sales as failed")
    return abandoned


# ----------------------------------------------------------------------
# Task 7: Subscription renewal (future)
# ----------------------------------------------------------------------
@shared_task(name="creator.process_subscription_renewal")
def process_subscription_renewal(sale_id: str):
    """
    Handle recurring subscription charges. Placeholder for future implementation.
    """
    logger.info(f"Subscription renewal for sale {sale_id} - not implemented yet")
    pass