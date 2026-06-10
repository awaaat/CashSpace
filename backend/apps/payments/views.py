# apps/payments/views.py
# ============================================================
# REST API views for the CashSpace payments app.
#
# Supports multi‑chain / multi‑currency payments via PayRam.
#
# Endpoints:
#   POST   /api/v1/payments/initiate/           → Start a payment session
#   GET    /api/v1/payments/                    → User's payment history
#   GET    /api/v1/payments/<id>/               → Single payment detail
#   GET    /api/v1/payments/<id>/status/        → Poll latest status from PayRam
#   POST   /api/v1/payments/webhook/            → PayRam webhook receiver (HMAC‑verified)
#   GET    /api/v1/payments/admin/              → All payments (staff only)
#
# Commission flow (operator keeps 30% of USD):
#   User pays $X → PayRam settles $X into our cold wallet → we keep 30% → payout 70%
#   The payout is sent in crypto (user's chosen blockchain/currency) after commission.
# ============================================================

import json
import logging
from decimal import Decimal

from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import AuditLog
from apps.core.permissions import IsActiveUser, IsOwnerOrAdmin

from .models import Payment, UserCryptoWallet, WebhookEvent
from .payram_client import PayRamError, payram
from .serializers import (
    AdminPaymentSerializer,
    InitiatePaymentSerializer,
    PaymentDetailSerializer,
    PaymentSerializer,
)
from .tasks import process_payout_after_payment, send_payment_confirmation_email

logger = logging.getLogger("apps.payments")


class PaymentRateThrottle(UserRateThrottle):
    rate = "10/minute"
    scope = "payment"


def get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


# ── User Payment Views ────────────────────────────────────────────────────────

class InitiatePaymentView(APIView):
    """
    POST /api/v1/payments/initiate/

    Creates a PayRam payment session and returns the hosted checkout URL.

    The user must have a saved crypto wallet (blockchain + currency + address)
    that will receive the payout. The user selects which wallet to use for this
    payment, and the system captures that decision.

    Request body:
        {
            "amount_usd": 100.00,
            "wallet_id": "uuid"                 # ID of UserCryptoWallet entry
        }

    Response:
        {
            "payment_id": "uuid",
            "payram_payment_url": "https://your-payram-server.com/payments?...",
            "reference_id": "c80f5363-...",
            "amount_usd": "100.00",
            "commission_usd": "30.00",
            "payout_usd_equivalent": "70.00",
            "commission_rate_pct": 30,
            "blockchain_code": "TRX",
            "currency_code": "USDT",
            "destination_wallet": "T...",
            "status": "OPEN"
        }

    Note: The user should be redirected to `payram_payment_url` to complete
    their card / crypto payment on PayRam's hosted checkout page.
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    throttle_classes = [PaymentRateThrottle]

    def post(self, request):
        serializer = InitiatePaymentSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        amount_usd = serializer.validated_data["amount_usd"]
        wallet_id = serializer.validated_data["wallet_id"]
        user = request.user

        # Retrieve the selected wallet (must belong to the user and be active)
        try:
            wallet = UserCryptoWallet.objects.get(
                id=wallet_id, user=user, is_active=True
            )
        except UserCryptoWallet.DoesNotExist:
            return Response(
                {"detail": "Selected wallet not found or inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Create local Payment record ───────────────────────────────────────
        payment = Payment(
            user=user,
            amount_usd=amount_usd,
            blockchain_code=wallet.blockchain_code,
            currency_code=wallet.currency_code,
            destination_wallet=wallet.wallet_address,
            status=Payment.Status.PENDING,
        )
        # Pre‑calculate commission in USD
        payment.calculate_commission()
        payment.save()

        # ── Create PayRam payment session (full amount) ───────────────────────
        # The full amount settles into our cold wallet. The payout amount
        # (after commission) will be sent later to the user's crypto wallet.
        try:
            result = payram.initiate_payment(
                customer_email=user.email,
                customer_id=str(user.id),
                amount_in_usd=amount_usd,
            )

            payment.payram_reference_id = result["reference_id"]
            payment.payram_payment_url = result["url"]
            payment.status = Payment.Status.OPEN
            payment.save(
                update_fields=["payram_reference_id", "payram_payment_url", "status"]
            )

            AuditLog.objects.create(
                user=user,
                action=AuditLog.Action.PAYMENT_INITIATED,
                ip_address=get_client_ip(request),
                metadata={
                    "payment_id": str(payment.id),
                    "amount_usd": str(amount_usd),
                    "commission_usd": str(payment.commission_usd),
                    "payout_usd_equivalent": str(payment.payout_usd_equivalent),
                    "blockchain_code": wallet.blockchain_code,
                    "currency_code": wallet.currency_code,
                    "destination_wallet": wallet.wallet_address,
                    "reference_id": result["reference_id"],
                },
            )

            return Response(
                {
                    "payment_id": str(payment.id),
                    "payram_payment_url": result["url"],
                    "reference_id": result["reference_id"],
                    "amount_usd": str(amount_usd),
                    "commission_usd": str(payment.commission_usd),
                    "payout_usd_equivalent": str(payment.payout_usd_equivalent),
                    "commission_rate_pct": int(payment.commission_rate * 100),
                    "blockchain_code": wallet.blockchain_code,
                    "currency_code": wallet.currency_code,
                    "destination_wallet": wallet.wallet_address,
                    "status": payment.status,
                },
                status=status.HTTP_201_CREATED,
            )

        except PayRamError as exc:
            logger.error(
                "PayRam error creating payment | user=%s | error=%s",
                user.email,
                exc,
            )
            payment.status = Payment.Status.FAILED
            payment.error_message = str(exc)
            payment.save(update_fields=["status", "error_message"])
            return Response(
                {"detail": "Failed to create payment session. Please try again."},
                status=status.HTTP_502_BAD_GATEWAY,
            )


class PaymentListView(generics.ListAPIView):
    """GET /api/v1/payments/ — current user's payment history."""

    serializer_class = PaymentSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    filterset_fields = ["status", "blockchain_code", "currency_code", "payout_status"]
    ordering_fields = ["created_at", "amount_usd"]

    def get_queryset(self):
        return Payment.objects.filter(user=self.request.user).order_by("-created_at")


class PaymentDetailView(generics.RetrieveAPIView):
    """GET /api/v1/payments/<id>/ — detail for one payment."""

    serializer_class = PaymentDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsOwnerOrAdmin]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Payment.objects.all()
        return Payment.objects.filter(user=self.request.user)


class CheckPaymentStatusView(APIView):
    """
    GET /api/v1/payments/<id>/status/

    Polls PayRam for the latest status of a specific payment.
    Use this for frontend polling while the user is on the PayRam
    checkout page, until you receive a FILLED or terminal status.

    Returns both the payment status and the payout status so the
    frontend can display the full state to the user.
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    throttle_classes = [PaymentRateThrottle]

    def get(self, request, pk):
        try:
            payment = Payment.objects.get(pk=pk, user=request.user)
        except Payment.DoesNotExist:
            return Response(
                {"detail": "Payment not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # If already terminal, return cached state without hitting PayRam
        if payment.is_terminal:
            return Response(
                {
                    "status": payment.status,
                    "payout_status": payment.payout_status,
                    "is_terminal": True,
                    "payout_is_terminal": payment.payout_is_terminal,
                    "commission_usd": str(payment.commission_usd or ""),
                    "payout_usd_equivalent": str(payment.payout_usd_equivalent or ""),
                    "payout_crypto_amount": str(payment.payout_crypto_amount or ""),
                    "blockchain_code": payment.blockchain_code,
                    "currency_code": payment.currency_code,
                }
            )

        if not payment.payram_reference_id:
            return Response(
                {
                    "status": payment.status,
                    "payout_status": payment.payout_status,
                    "is_terminal": False,
                    "payout_is_terminal": payment.payout_is_terminal,
                    "blockchain_code": payment.blockchain_code,
                    "currency_code": payment.currency_code,
                }
            )

        # ── Poll PayRam for latest payment status ─────────────────────────────
        try:
            result = payram.get_payment_request(payment.payram_reference_id)
            payram_state = result.get("paymentState", "")

            STATE_MAP = {
                "OPEN": Payment.Status.OPEN,
                "FILLED": Payment.Status.FILLED,
                "PARTIALLY_FILLED": Payment.Status.PARTIALLY_FILLED,
                "OVER_FILLED": Payment.Status.OVER_FILLED,
                "CANCELLED": Payment.Status.CANCELLED,
            }

            new_status = STATE_MAP.get(payram_state, payment.status)

            if new_status != payment.status:
                payment.status = new_status
                payment.payram_raw_status = payram_state
                payment.save(update_fields=["status", "payram_raw_status", "updated_at"])

                if new_status == Payment.Status.FILLED and payment.needs_payout:
                    # ── Trigger payout to user's wallet ───────────────────────
                    process_payout_after_payment.delay(str(payment.id))

                    AuditLog.objects.create(
                        user=request.user,
                        action=AuditLog.Action.PAYMENT_COMPLETED,
                        metadata={
                            "payment_id": str(payment.id),
                            "source": "status_poll",
                        },
                    )

        except PayRamError as exc:
            logger.warning(
                "Status poll failed | payment_id=%s | error=%s",
                payment.id,
                exc,
            )
            # Return cached state on poll error – don't 500 the frontend

        # Re‑fetch to return the freshest data (payout task may have updated)
        payment.refresh_from_db()

        return Response(
            {
                "status": payment.status,
                "payout_status": payment.payout_status,
                "payram_state": payment.payram_raw_status,
                "is_terminal": payment.is_terminal,
                "payout_is_terminal": payment.payout_is_terminal,
                "commission_usd": str(payment.commission_usd or ""),
                "payout_usd_equivalent": str(payment.payout_usd_equivalent or ""),
                "payout_crypto_amount": str(payment.payout_crypto_amount or ""),
                "blockchain_code": payment.blockchain_code,
                "currency_code": payment.currency_code,
                "destination_wallet": payment.destination_wallet,
            }
        )


# ── Webhook ───────────────────────────────────────────────────────────────────

@method_decorator(csrf_exempt, name="dispatch")
class PayRamWebhookView(APIView):
    """
    POST /api/v1/payments/webhook/

    Receives real-time payment state events from PayRam.

    Security:
      - HMAC-SHA256 signature verified via API‑Key header (direct comparison).
      - Invalid signatures are logged but still return 200 so PayRam
        doesn't retry indefinitely (the event is NOT processed).
      - All raw events are stored in WebhookEvent for audit/replay.

    When a payment reaches FILLED:
      - process_payout_after_payment Celery task is triggered.
      - Task deducts 30% commission and sends remaining amount in crypto
        to the user's saved wallet (blockchain/currency chosen at initiation).
    """

    permission_classes = [permissions.AllowAny]  # Auth is done via HMAC signature

    def post(self, request):
        raw_body = request.body

        # ── Verify signature (API‑Key header, direct comparison) ───────────────
        signature_header = request.headers.get("API-Key", "")
        sig_valid = payram.verify_webhook_signature(raw_body, signature_header)

        # ── Parse payload ─────────────────────────────────────────────────────
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            logger.warning("Webhook received invalid JSON")
            return Response({"detail": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

        event_type = payload.get("event", "")
        reference_id = payload.get("reference_id", "")
        payment_state = payload.get("paymentState", "")

        # ── Look up associated payment ────────────────────────────────────────
        payment = None
        if reference_id:
            try:
                payment = Payment.objects.select_related("user").get(
                    payram_reference_id=reference_id
                )
            except Payment.DoesNotExist:
                logger.warning(
                    "Webhook received for unknown reference_id=%s", reference_id
                )

        # ── Log raw webhook event (always, even if invalid sig) ───────────────
        webhook_event = WebhookEvent.objects.create(
            payment=payment,
            payram_reference_id=reference_id,
            event_type=event_type,
            payload=payload,
            signature_valid=sig_valid,
        )

        # ── Reject invalid signatures ─────────────────────────────────────────
        if not sig_valid:
            logger.warning(
                "Invalid webhook signature | reference_id=%s | "
                "event=%s | sig_header=%s",
                reference_id,
                event_type,
                signature_header[:16] + "..." if signature_header else "(empty)",
            )
            # Return 200 so PayRam stops retrying — but do NOT process
            return Response({"detail": "ok"})

        # ── Update payment status ─────────────────────────────────────────────
        if payment and payment_state:
            STATE_MAP = {
                "OPEN": Payment.Status.OPEN,
                "FILLED": Payment.Status.FILLED,
                "PARTIALLY_FILLED": Payment.Status.PARTIALLY_FILLED,
                "OVER_FILLED": Payment.Status.OVER_FILLED,
                "CANCELLED": Payment.Status.CANCELLED,
            }
            new_status = STATE_MAP.get(payment_state, payment.status)

            if not payment.is_terminal:
                payment.status = new_status
                payment.payram_raw_status = payment_state
                payment.last_webhook_at = timezone.now()
                payment.webhook_count += 1
                payment.save(
                    update_fields=[
                        "status",
                        "payram_raw_status",
                        "last_webhook_at",
                        "webhook_count",
                        "updated_at",
                    ]
                )

                webhook_event.processed = True
                webhook_event.save(update_fields=["processed"])

                if new_status == Payment.Status.FILLED and payment.needs_payout:
                    # ── Trigger payout to user's wallet ───────────────────────
                    # The task will:
                    #   1. Calculate commission_usd = amount_usd × 0.30
                    #   2. payout_usd = amount_usd × 0.70
                    #   3. Fetch current exchange rate (or use stablecoin 1:1)
                    #   4. Call payram.create_payout() with the user's blockchain,
                    #      currency, and address
                    #   5. Poll payout status until completed/failed
                    #   6. Send confirmation email
                    process_payout_after_payment.delay(str(payment.id))

                    logger.info(
                        "Payment FILLED via webhook — payout task queued "
                        "| reference_id=%s | user=%s | amount=$%.2f "
                        "| blockchain=%s | currency=%s | destination=%s",
                        reference_id,
                        payment.user.email,
                        payment.amount_usd,
                        payment.blockchain_code,
                        payment.currency_code,
                        payment.destination_wallet,
                    )

                    AuditLog.objects.create(
                        user=payment.user,
                        action=AuditLog.Action.PAYMENT_COMPLETED,
                        metadata={
                            "payment_id": str(payment.id),
                            "reference_id": reference_id,
                            "source": "webhook",
                            "blockchain": payment.blockchain_code,
                            "currency": payment.currency_code,
                        },
                    )

        return Response({"detail": "ok"})


# ── Admin Views ───────────────────────────────────────────────────────────────

class AdminPaymentListView(generics.ListAPIView):
    """
    GET /api/v1/payments/admin/

    All payments across all users. Staff only.
    Includes full commission breakdown and payout tracking.
    """

    serializer_class = AdminPaymentSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filterset_fields = [
        "status",
        "blockchain_code",
        "currency_code",
        "payout_status",
        "user",
    ]
    search_fields = [
        "user__email",
        "payram_reference_id",
        "destination_wallet",
        "payram_payout_id",
    ]
    ordering_fields = ["created_at", "amount_usd", "status", "payout_status"]

    def get_queryset(self):
        return Payment.objects.select_related("user").order_by("-created_at")