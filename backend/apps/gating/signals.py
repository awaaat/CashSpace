"""
apps/gating/signals.py
======================
Enterprise‑grade Django signals for the gating app.

Listens to:
  - Payment status change (when payment becomes FILLED)
  - Post‑save of AccessGrant (audit, initialisation)
  - Pre‑delete of AccessToken (optional cleanup)

Key responsibilities:
  1. On payment completion (FILLED):
     - Activates the associated AccessGrant.
     - Sets access expiry based on asset configuration.
     - Generates an AccessToken (signed, with expiry & max uses).
     - Triggers asynchronous tasks: email delivery, webhook, affiliate commission, drip content.
     - Updates dynamic pricing velocity cache.
  2. On grant creation: logs and pre‑warms any necessary data.
  3. On asset price change: invalidates cached pricing.

All operations are idempotent, wrapped in database transactions, and use
`transaction.on_commit()` to ensure Celery tasks run only after the transaction is committed.
"""

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone
from django.core.cache import cache

from apps.payments.models import Payment
from .models import AccessGrant, AccessToken, GatedAsset
from .tokens import create_access_token
from .tasks import (
    send_access_grant_email,
    call_grant_webhook,
    affiliate_commission_payout,
    process_step_unlock,
)

logger = logging.getLogger("apps.gating.signals")


# ----------------------------------------------------------------------
# Helper: schedule task after transaction commit
# ----------------------------------------------------------------------
def _after_commit(func, *args, **kwargs):
    """Safely schedule a function to run after the current database transaction commits."""
    transaction.on_commit(lambda: func(*args, **kwargs))


# ----------------------------------------------------------------------
# Signal: Payment → Activate Grant
# ----------------------------------------------------------------------
@receiver(post_save, sender=Payment)
def on_payment_filled(sender, instance, created, **kwargs):
    """
    When a Payment reaches FILLED status, activate the linked AccessGrant.
    Idempotent: only processes if grant exists and is not already GRANTED.
    """
    # Only act on status change to FILLED
    if instance.status != Payment.Status.FILLED:
        return

    # Check if this payment is linked to an AccessGrant
    # Related name defined in AccessGrant.payment → 'access_grant'
    try:
        grant = instance.access_grant
    except AccessGrant.DoesNotExist:
        # Not a gated asset purchase – ignore
        return

    # Idempotency guard: already granted
    if grant.status == AccessGrant.Status.GRANTED:
        logger.info(f"Signal: Grant {grant.id} already GRANTED, skipping duplicate activation")
        return

    # Prevent race conditions: double-check payment status again inside transaction
    with transaction.atomic():
        # Refresh from DB to avoid stale state
        grant.refresh_from_db()
        if grant.status == AccessGrant.Status.GRANTED:
            return

        asset = grant.asset

        # Calculate access expiry based on asset's grant duration
        access_expires_at = None
        if asset.grant_duration_value > 0 and asset.grant_duration_unit:
            value = asset.grant_duration_value
            unit = asset.grant_duration_unit
            if unit == GatedAsset.AccessDurationUnit.HOURS:
                delta = timedelta(hours=value)
            elif unit == GatedAsset.AccessDurationUnit.DAYS:
                delta = timedelta(days=value)
            elif unit == GatedAsset.AccessDurationUnit.WEEKS:
                delta = timedelta(weeks=value)
            elif unit == GatedAsset.AccessDurationUnit.MONTHS:
                delta = timedelta(days=value * 30)
            elif unit == GatedAsset.AccessDurationUnit.YEARS:
                delta = timedelta(days=value * 365)
            else:
                delta = None
            if delta:
                access_expires_at = timezone.now() + delta

        # Update grant
        grant.status = AccessGrant.Status.GRANTED
        grant.access_expires_at = access_expires_at
        grant.save(update_fields=["status", "access_expires_at"])

        # Generate access token
        token_expires_seconds = asset.token_expires_after_grant_value * 3600 if asset.token_expires_after_grant_value else None
        token_str = create_access_token(
            asset_id=str(asset.id),
            grant_id=str(grant.id),
            buyer_email=grant.email,
            expires_in_seconds=token_expires_seconds,
            max_uses=asset.token_max_uses,
            custom_claims={
                "asset_type": asset.asset_type,
                "pricing_type": asset.pricing_type,
            }
        )

        # Store token in database
        token_obj = AccessToken.objects.create(
            grant=grant,
            token=token_str,
            expires_at=timezone.now() + timedelta(seconds=token_expires_seconds) if token_expires_seconds else None,
            max_uses=asset.token_max_uses,
        )
        logger.info(f"Grant {grant.id} activated. Token {token_obj.token[:16]}... created.")

    # ------------------------------------------------------------------
    # Asynchronous post‑activation tasks (run after commit)
    # ------------------------------------------------------------------
    _after_commit(send_access_grant_email.delay, str(grant.id))
    _after_commit(call_grant_webhook.delay, str(grant.id))

    if grant.affiliate_code:
        _after_commit(affiliate_commission_payout.delay, str(grant.id))

    # Drip content scheduling
    if asset.steps and len(asset.steps) > 0:
        first_step = asset.steps[0]
        delay_days = first_step.get("delay_days", 0)
        if delay_days == 0:
            _after_commit(process_step_unlock.delay, str(grant.id), 0)
        else:
            from celery import current_app
            _after_commit(
                current_app.send_task,
                "gating.process_step_unlock",
                args=[str(grant.id), 0],
                countdown=delay_days * 86400
            )

    # Update dynamic pricing sales velocity (lightweight, no task needed)
    if asset.dynamic_pricing_enabled:
        today_key = timezone.now().strftime("%Y%m%d")
        cache_key = f"gating:asset_sales_velocity:{asset.id}:{today_key}"
        try:
            cache.incr(cache_key)
        except Exception as e:
            logger.warning(f"Failed to update velocity cache for asset {asset.id}: {e}")

    # Optional: send admin alert for high‑value grants (if configured)
    high_value_threshold = getattr(settings, "GATING_HIGH_VALUE_ALERT_THRESHOLD", 500)
    if grant.amount_usd >= high_value_threshold:
        from .tasks import send_admin_alert
        _after_commit(send_admin_alert.delay, str(grant.id), high_value_threshold)


# ----------------------------------------------------------------------
# Signal: Grant creation (audit & pre‑warm)
# ----------------------------------------------------------------------
@receiver(post_save, sender=AccessGrant)
def on_grant_created(sender, instance, created, **kwargs):
    """Log grant creation and optionally pre‑warm any caches."""
    if created:
        logger.info(f"AccessGrant created: {instance.id} for {instance.email} on asset {instance.asset.id}")
        # Pre‑warm any data that will be needed on payment completion
        # (e.g., load asset settings into cache)
        asset_key = f"gating:asset:{instance.asset.id}"
        cache.set(asset_key, instance.asset, timeout=3600)


# ----------------------------------------------------------------------
# Signal: Asset price change – invalidate caches
# ----------------------------------------------------------------------
@receiver(post_save, sender=GatedAsset)
def on_asset_updated(sender, instance, created, **kwargs):
    """When asset price or configuration changes, clear related caches."""
    if not created:
        # Clear asset detail cache
        cache.delete(f"gating:asset:{instance.id}")
        # Clear any cached price display
        cache.delete_pattern(f"gating:asset_price:*{instance.id}*")
        logger.debug(f"Invalidated caches for asset {instance.id}")


# ----------------------------------------------------------------------
# Signal: Token usage (optional – can be used to update last_used_at)
# Not implemented here because token consumption is handled inside verify.py
# ----------------------------------------------------------------------