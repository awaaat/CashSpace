"""
apps/merchants/tasks.py
========================
Celery tasks for merchant post-payment automation.

Task inventory:
  trigger_post_payment_actions   — entry point; fetches all active actions
                                   for the product and dispatches each one
  retry_webhook_delivery         — retries a failed WebhookDeliveryLog entry
  notify_merchant_of_sale        — emails merchant a sale notification

Action runners (sync helpers inside trigger_post_payment_actions):
  _run_telegram_invite
  _run_email_delivery
  _run_webhook
  _run_discord_role
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import timedelta

import requests
from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger("apps.merchants")

MAX_RETRIES = 4
RETRY_BACKOFF = 60  # seconds, doubled each retry


# ══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF,
    name="merchants.trigger_post_payment_actions",
)
def trigger_post_payment_actions(self, checkout_id: str) -> None:
    """
    Main automation task. Fires all PostPaymentActions for a completed checkout.

    Called by:
      - payments.tasks.process_payout_after_payment (automatically on FILLED)
      - merchants.views.RetriggerAutomationView (manual retrigger by merchant)
      - TestCompleteView / TestSaleView (test mode — skips payment check)

    Idempotency: exits immediately if checkout.automation_triggered is True,
    unless the merchant explicitly reset it (retrigger flow).
    """
    from .models import CustomerCheckout, PostPaymentAction

    try:
        checkout = (
            CustomerCheckout.objects
            .select_related("product", "product__merchant", "payment")
            .get(id=checkout_id)
        )
    except CustomerCheckout.DoesNotExist:
        logger.error("trigger_post_payment_actions: checkout %s not found", checkout_id)
        return

    # ── Idempotency guard ─────────────────────────────────────────────────────
    if checkout.automation_triggered:
        logger.info(
            "Automation already triggered for checkout %s — skipping", checkout_id
        )
        return

    # ── Payment check — skip for test checkouts ───────────────────────────────
    payment = checkout.payment
    if not checkout.is_test:
        if not payment or payment.status != "FILLED":
            logger.warning(
                "trigger_post_payment_actions called for checkout %s but payment status=%s",
                checkout_id,
                payment.status if payment else "None",
            )
            return

    product = checkout.product
    merchant = product.merchant

    actions = PostPaymentAction.objects.filter(
        product=product,
        is_active=True,
    ).order_by("priority")

    if not actions.exists():
        logger.info(
            "No active post-payment actions for product %s — marking complete",
            product.slug,
        )
        _mark_automation_complete(checkout)
        return

    errors = []

    for action in actions:
        try:
            logger.info(
                "Running action %s | type=%s | checkout=%s | buyer=%s | test=%s",
                action.id, action.action_type, checkout_id, checkout.email, checkout.is_test,
            )

            if action.action_type == PostPaymentAction.ActionType.TELEGRAM_INVITE:
                _run_telegram_invite(checkout, action)

            elif action.action_type == PostPaymentAction.ActionType.EMAIL_DELIVERY:
                _run_email_delivery(checkout, action, merchant)

            elif action.action_type == PostPaymentAction.ActionType.WEBHOOK:
                _run_webhook(checkout, action, payment)

            elif action.action_type == PostPaymentAction.ActionType.DISCORD_ROLE:
                _run_discord_role(checkout, action)

            else:
                logger.warning("Unknown action type: %s", action.action_type)

        except Exception as exc:
            error_msg = f"{action.action_type}: {exc}"
            logger.error(
                "Action %s failed | checkout=%s | error=%s",
                action.action_type, checkout_id, exc,
            )
            errors.append(error_msg)

    if errors:
        combined = " | ".join(errors)
        checkout.automation_error = combined
        checkout.save(update_fields=["automation_error"])

        try:
            raise self.retry(
                exc=Exception(combined),
                countdown=RETRY_BACKOFF * (2 ** self.request.retries),
            )
        except self.MaxRetriesExceededError:
            logger.critical(
                "Automation permanently failed after %d retries | checkout=%s | errors=%s",
                MAX_RETRIES, checkout_id, combined,
            )
            _mark_automation_complete(checkout, error=combined)
            _alert_admin_automation_failure(checkout, combined)
        return

    _mark_automation_complete(checkout)

    # Only email merchant for live sales
    if not checkout.is_test:
        notify_merchant_of_sale.delay(checkout_id)

    logger.info(
        "All post-payment actions complete | checkout=%s | buyer=%s | product=%s | test=%s",
        checkout_id, checkout.email, product.name, checkout.is_test,
    )


# ══════════════════════════════════════════════════════════════════════════════
# WEBHOOK RETRY TASK
# ══════════════════════════════════════════════════════════════════════════════

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="merchants.retry_webhook_delivery",
)
def retry_webhook_delivery(self, log_id: str) -> None:
    """
    Retry a failed WebhookDeliveryLog entry.

    Called by:
      - WebhookDeliveryLogRetryView (manual retry from merchant dashboard)
      - Celery beat (scheduled retry for logs with next_retry_at <= now)

    Records a new attempt on the existing log — does NOT create a new log entry.
    Updates status to SUCCESS or FAILED depending on outcome.
    """
    from .models import WebhookDeliveryLog

    try:
        log = WebhookDeliveryLog.objects.select_related(
            "merchant", "checkout"
        ).get(id=log_id)
    except WebhookDeliveryLog.DoesNotExist:
        logger.error("retry_webhook_delivery: log %s not found", log_id)
        return

    if not log.can_retry:
        logger.warning(
            "Log %s cannot be retried (status=%s, attempts=%d)",
            log_id, log.status, log.attempt_number,
        )
        return

    log.status = WebhookDeliveryLog.Status.RETRYING
    log.attempt_number += 1
    log.save(update_fields=["status", "attempt_number"])

    body_bytes = json.dumps(log.request_body, separators=(",", ":")).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        **{k: v for k, v in log.request_headers.items() if k != "X-CashSpace-Signature"},
    }

    # Recompute signature if merchant has a webhook_secret
    webhook_secret = log.merchant.webhook_secret
    if webhook_secret:
        sig = hmac.new(
            webhook_secret.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()
        headers["X-CashSpace-Signature"] = f"sha256={sig}"

    start = time.monotonic()
    try:
        resp = requests.post(
            log.endpoint_url,
            data=body_bytes,
            headers=headers,
            timeout=10,
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        log.response_status_code = resp.status_code
        log.response_body = resp.text[:2048]
        log.duration_ms = duration_ms

        if 200 <= resp.status_code < 300:
            log.status = WebhookDeliveryLog.Status.SUCCESS
            log.error_message = ""
            log.next_retry_at = None
            logger.info(
                "Webhook retry succeeded | log=%s | attempt=%d | status=%d",
                log_id, log.attempt_number, resp.status_code,
            )
        else:
            raise requests.exceptions.HTTPError(
                f"Non-2xx response: {resp.status_code}", response=resp
            )

    except Exception as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.duration_ms = duration_ms
        log.error_message = str(exc)

        if log.attempt_number >= WebhookDeliveryLog.MAX_ATTEMPTS:
            log.status = WebhookDeliveryLog.Status.EXHAUSTED
            log.next_retry_at = None
            logger.error(
                "Webhook exhausted max retries | log=%s | attempts=%d",
                log_id, log.attempt_number,
            )
        else:
            delay = WebhookDeliveryLog.RETRY_DELAYS[
                min(log.attempt_number - 1, len(WebhookDeliveryLog.RETRY_DELAYS) - 1)
            ]
            log.status = WebhookDeliveryLog.Status.FAILED
            log.next_retry_at = timezone.now() + timedelta(seconds=delay)
            logger.warning(
                "Webhook retry failed | log=%s | attempt=%d | next_retry_in=%ds",
                log_id, log.attempt_number, delay,
            )

    log.save(update_fields=[
        "status", "attempt_number", "response_status_code",
        "response_body", "duration_ms", "error_message", "next_retry_at",
    ])


# ══════════════════════════════════════════════════════════════════════════════
# ACTION RUNNERS
# ══════════════════════════════════════════════════════════════════════════════

def _run_telegram_invite(checkout, action) -> None:
    """
    Send buyer their Telegram group invite link via email.

    Config keys:
        invite_link  (required) — the t.me/+... invite URL
        message      (optional) — custom message body
    """
    config = action.config
    invite_link = config.get("invite_link", "")
    if not invite_link:
        raise ValueError("telegram_invite action missing 'invite_link' in config")

    product = checkout.product
    merchant = product.merchant
    custom_message = config.get("message", "")

    body = custom_message or (
        f"Hi {checkout.full_name or checkout.email},\n\n"
        f"Thank you for your purchase of {product.name}!\n\n"
        f"Click the link below to join the Telegram group:\n\n"
        f"{invite_link}\n\n"
        f"This link is personal to you — please don't share it.\n\n"
        f"— {merchant.business_name}"
    )

    send_mail(
        subject=f"Your access to {product.name} — Telegram invite",
        message=body,
        from_email=_get_from_email(merchant),
        recipient_list=[checkout.email],
        fail_silently=False,
    )

    logger.info(
        "Telegram invite sent | checkout=%s | email=%s",
        checkout.id, checkout.email,
    )


def _run_email_delivery(checkout, action, merchant) -> None:
    """
    Send buyer a fully custom email from the merchant.

    Config keys:
        subject         (required)
        body_template   (required) — supports {buyer_name}, {buyer_email},
                                     {product_name}, {merchant_name},
                                     {amount_usd}, {download_link}
        from_name       (optional)
        download_link   (optional)
    """
    config = action.config
    subject = config.get("subject")
    body_template = config.get("body_template")

    if not subject or not body_template:
        raise ValueError("email_delivery action missing 'subject' or 'body_template'")

    placeholders = {
        "buyer_name": checkout.full_name or checkout.email.split("@")[0],
        "buyer_email": checkout.email,
        "product_name": checkout.product.name,
        "merchant_name": merchant.business_name,
        "amount_usd": str(checkout.amount_usd),
        "download_link": config.get("download_link", ""),
        "telegram_group": config.get("telegram_group", ""),
        "discord_server": config.get("discord_server", ""),
    }

    try:
        body = body_template.format(**placeholders)
    except KeyError as e:
        raise ValueError(f"Unknown placeholder in body_template: {e}")

    send_mail(
        subject=subject,
        message=body,
        from_email=_get_from_email(merchant, config.get("from_name")),
        recipient_list=[checkout.email],
        fail_silently=False,
    )

    logger.info(
        "Email delivered | checkout=%s | email=%s | subject=%s",
        checkout.id, checkout.email, subject,
    )


def _run_webhook(checkout, action, payment) -> None:
    """
    POST buyer + payment data to the merchant's own server.

    Config keys:
        url     (required)
        secret  (optional) — HMAC-SHA256 signing secret

    Also logs the attempt to WebhookDeliveryLog for dashboard visibility.
    """
    from .models import WebhookDeliveryLog

    config = action.config
    url = config.get("url")
    if not url:
        raise ValueError("webhook action missing 'url' in config")

    merchant = checkout.product.merchant

    payload = {
        "event": "payment.completed",
        "checkout_id": str(checkout.id),
        "payment_id": str(payment.id) if payment else None,
        "product_slug": checkout.product.slug,
        "merchant_slug": merchant.slug,
        "buyer_email": checkout.email,
        "buyer_name": checkout.full_name,
        "telegram_username": checkout.telegram_username,
        "discord_username": checkout.discord_username,
        "phone_number": checkout.phone_number,
        "custom_field_value": checkout.custom_field_value,
        "amount_usd": str(checkout.amount_usd),
        "is_test": checkout.is_test,
        "paid_at": timezone.now().isoformat(),
    }

    body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    secret = config.get("secret", "") or merchant.webhook_secret
    if secret:
        sig = hmac.new(
            secret.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()
        headers["X-CashSpace-Signature"] = f"sha256={sig}"

    # Create the delivery log (pending)
    log = WebhookDeliveryLog.objects.create(
        merchant=merchant,
        checkout=checkout,
        event_type=WebhookDeliveryLog.EventType.PAYMENT_COMPLETED,
        is_test=checkout.is_test,
        endpoint_url=url,
        request_body=payload,
        request_headers={k: v for k, v in headers.items() if "signature" not in k.lower()},
        status=WebhookDeliveryLog.Status.PENDING,
        attempt_number=1,
    )

    start = time.monotonic()
    try:
        resp = requests.post(url, data=body_bytes, headers=headers, timeout=10)
        duration_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()

        log.response_status_code = resp.status_code
        log.response_body = resp.text[:2048]
        log.duration_ms = duration_ms
        log.status = WebhookDeliveryLog.Status.SUCCESS
        log.save(update_fields=[
            "response_status_code", "response_body", "duration_ms", "status"
        ])

        logger.info(
            "Merchant webhook delivered | checkout=%s | url=%s | status=%s",
            checkout.id, url, resp.status_code,
        )

    except requests.exceptions.Timeout:
        duration_ms = int((time.monotonic() - start) * 1000)
        _fail_webhook_log(log, "Timeout", duration_ms)
        raise Exception(f"Merchant webhook timed out: {url}")

    except requests.exceptions.HTTPError as e:
        duration_ms = int((time.monotonic() - start) * 1000)
        log.response_status_code = e.response.status_code if e.response else None
        log.response_body = e.response.text[:2048] if e.response else ""
        _fail_webhook_log(log, str(e), duration_ms)
        raise Exception(f"Merchant webhook HTTP error {e.response.status_code}: {url}")

    except requests.exceptions.ConnectionError:
        duration_ms = int((time.monotonic() - start) * 1000)
        _fail_webhook_log(log, "Connection error", duration_ms)
        raise Exception(f"Merchant webhook connection failed: {url}")


def _fail_webhook_log(log, error: str, duration_ms: int) -> None:
    """Update a WebhookDeliveryLog to FAILED state with retry scheduling."""
    from .models import WebhookDeliveryLog

    attempt = log.attempt_number
    if attempt >= WebhookDeliveryLog.MAX_ATTEMPTS:
        log.status = WebhookDeliveryLog.Status.EXHAUSTED
        log.next_retry_at = None
    else:
        delay = WebhookDeliveryLog.RETRY_DELAYS[
            min(attempt - 1, len(WebhookDeliveryLog.RETRY_DELAYS) - 1)
        ]
        log.status = WebhookDeliveryLog.Status.FAILED
        log.next_retry_at = timezone.now() + timedelta(seconds=delay)

    log.error_message = error
    log.duration_ms = duration_ms
    log.save(update_fields=[
        "status", "error_message", "duration_ms", "next_retry_at"
    ])


def _run_discord_role(checkout, action) -> None:
    """
    Grant a Discord role to the buyer via Discord REST API.

    Config keys:
        guild_id    (required)
        role_id     (required)
        bot_token   (required)
        message     (optional) — DM sent to buyer after role grant

    Note: buyer must already be in the server. Discord role assignment
    requires their numeric user ID, resolved by searching the guild by username.
    """
    config = action.config
    guild_id = config.get("guild_id")
    role_id = config.get("role_id")
    bot_token = config.get("bot_token")

    if not all([guild_id, role_id, bot_token]):
        raise ValueError("discord_role action missing guild_id, role_id, or bot_token")

    discord_username = checkout.discord_username
    if not discord_username:
        raise ValueError(
            f"Buyer {checkout.email} did not provide a Discord username"
        )

    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }
    base = "https://discord.com/api/v10"

    # Step 1: Find member by username
    search_resp = requests.get(
        f"{base}/guilds/{guild_id}/members/search",
        params={"query": discord_username, "limit": 5},
        headers=headers,
        timeout=10,
    )
    search_resp.raise_for_status()
    members = search_resp.json()

    target_member = next(
        (
            m for m in members
            if m.get("user", {}).get("username", "").lower() == discord_username.lower()
            or m.get("user", {}).get("global_name", "").lower() == discord_username.lower()
        ),
        None,
    )

    if not target_member:
        raise ValueError(
            f"Discord user '{discord_username}' not found in guild {guild_id}. "
            "They must join the server before payment for role assignment to work."
        )

    user_id = target_member["user"]["id"]

    # Step 2: Grant the role
    role_resp = requests.put(
        f"{base}/guilds/{guild_id}/members/{user_id}/roles/{role_id}",
        headers=headers,
        timeout=10,
    )
    role_resp.raise_for_status()

    logger.info(
        "Discord role granted | checkout=%s | discord_user=%s | guild=%s | role=%s",
        checkout.id, discord_username, guild_id, role_id,
    )

    # Step 3: Optional DM
    dm_message = config.get("message")
    if dm_message:
        try:
            dm_resp = requests.post(
                f"{base}/users/@me/channels",
                json={"recipient_id": user_id},
                headers=headers,
                timeout=10,
            )
            dm_resp.raise_for_status()
            channel_id = dm_resp.json()["id"]
            requests.post(
                f"{base}/channels/{channel_id}/messages",
                json={"content": dm_message},
                headers=headers,
                timeout=10,
            )
            logger.info("Discord DM sent | checkout=%s | user=%s", checkout.id, discord_username)
        except Exception as dm_exc:
            # DM failure is non-fatal — role was already granted
            logger.warning(
                "Discord DM failed (non-fatal) | checkout=%s | error=%s",
                checkout.id, dm_exc,
            )


# ══════════════════════════════════════════════════════════════════════════════
# MERCHANT SALE NOTIFICATION
# ══════════════════════════════════════════════════════════════════════════════

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    name="merchants.notify_merchant_of_sale",
)
def notify_merchant_of_sale(self, checkout_id: str) -> None:
    """
    Email the merchant when a live sale completes.
    Only fires for is_test=False checkouts.
    """
    from .models import CustomerCheckout

    try:
        checkout = CustomerCheckout.objects.select_related(
            "product", "product__merchant", "product__merchant__user"
        ).get(id=checkout_id)
    except CustomerCheckout.DoesNotExist:
        logger.error("notify_merchant_of_sale: checkout %s not found", checkout_id)
        return

    if checkout.is_test:
        logger.info("Skipping sale notification for test checkout %s", checkout_id)
        return

    merchant = checkout.product.merchant
    merchant_email = merchant.user.email
    product = checkout.product

    buyer_info_lines = [f"  Email:        {checkout.email}"]
    if checkout.full_name:
        buyer_info_lines.append(f"  Name:         {checkout.full_name}")
    if checkout.telegram_username:
        buyer_info_lines.append(f"  Telegram:     @{checkout.telegram_username}")
    if checkout.discord_username:
        buyer_info_lines.append(f"  Discord:      {checkout.discord_username}")
    if checkout.phone_number:
        buyer_info_lines.append(f"  Phone:        {checkout.phone_number}")
    if checkout.custom_field_value and product.collect_custom_field:
        buyer_info_lines.append(f"  {product.collect_custom_field}: {checkout.custom_field_value}")

    buyer_info = "\n".join(buyer_info_lines)
    commission_rate = merchant.get_effective_commission_rate()
    payout_usd = checkout.amount_usd * (1 - commission_rate)
    commission_rate_pct = int(commission_rate * 100)

    message = (
        f"New sale on CashSpace!\n\n"
        f"Product:          {product.name}\n"
        f"Amount:           ${checkout.amount_usd}\n"
        f"Your payout:      ${payout_usd:.2f} (after {commission_rate_pct}% fee)\n"
        f"Settlement:       {merchant.settlement_currency} on {merchant.settlement_blockchain}\n\n"
        f"Buyer details:\n{buyer_info}\n\n"
        f"Automation:       {'✓ Triggered' if checkout.automation_triggered else '⚠ Pending'}\n\n"
        f"View full details in your CashSpace merchant dashboard.\n\n"
        f"— CashSpace"
    )

    try:
        send_mail(
            subject=f"💰 New sale: {product.name} — ${checkout.amount_usd}",
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[merchant_email],
            fail_silently=False,
        )
        logger.info(
            "Sale notification sent | merchant=%s | checkout=%s | amount=$%s",
            merchant_email, checkout_id, checkout.amount_usd,
        )
    except Exception as exc:
        logger.error("Failed to send sale notification: %s", exc)
        raise self.retry(exc=exc)


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _mark_automation_complete(checkout, error: str = "") -> None:
    from .models import CustomerCheckout

    checkout.automation_triggered = True
    checkout.automation_triggered_at = timezone.now()
    checkout.automation_error = error

    if not error and (checkout.is_test or (checkout.payment and checkout.payment.status == "FILLED")):
        checkout.status = CustomerCheckout.Status.COMPLETED

    checkout.save(update_fields=[
        "automation_triggered",
        "automation_triggered_at",
        "automation_error",
        "status",
    ])


def _get_from_email(merchant, from_name: str = None) -> str:
    name = from_name or merchant.business_name
    base = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@cashspace.com")
    if "<" in base and ">" in base:
        base = base.split("<")[1].rstrip(">")
    return f"{name} via CashSpace <{base}>"


def _alert_admin_automation_failure(checkout, error: str) -> None:
    admins = getattr(settings, "ADMINS", [])
    if not admins:
        return

    admin_emails = [email for _, email in admins]
    try:
        send_mail(
            subject=f"[CashSpace] Automation failed: {checkout.product.name} | {checkout.email}",
            message=(
                f"Post-payment automation permanently failed.\n\n"
                f"Checkout ID:  {checkout.id}\n"
                f"Buyer:        {checkout.email}\n"
                f"Product:      {checkout.product.name}\n"
                f"Merchant:     {checkout.product.merchant.business_name}\n"
                f"Is Test:      {checkout.is_test}\n"
                f"Error:        {error}\n\n"
                f"Trigger manually from the merchant dashboard."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=admin_emails,
            fail_silently=True,
        )
    except Exception as exc:
        logger.error("Failed to send admin automation alert: %s", exc)