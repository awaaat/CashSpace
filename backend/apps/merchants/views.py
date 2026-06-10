"""
apps/merchants/views.py
========================
REST API views for the merchant layer.

Endpoint groups:
  PUBLIC (no auth)
    GET  /pay/<merchant_slug>/
    GET  /pay/<merchant_slug>/<product_slug>/
    POST /pay/<merchant_slug>/<product_slug>/checkout/
    GET  /pay/<merchant_slug>/<product_slug>/checkout/<id>/status/
    POST /pay/<merchant_slug>/<product_slug>/checkout/<id>/test-complete/

  MERCHANT (authenticated)
    POST   /merchants/register/
    GET    /merchants/me/
    PATCH  /merchants/me/
    GET    /merchants/me/analytics/
    GET    /merchants/me/sales/
    GET    /merchants/me/sales/<id>/
    POST   /merchants/me/sales/<id>/retrigger/
    GET    /merchants/me/products/
    POST   /merchants/me/products/
    GET    /merchants/me/products/<id>/
    PATCH  /merchants/me/products/<id>/
    DELETE /merchants/me/products/<id>/
    GET    /merchants/me/products/<id>/actions/
    POST   /merchants/me/products/<id>/actions/
    PATCH  /merchants/me/products/<id>/actions/<aid>/
    DELETE /merchants/me/products/<id>/actions/<aid>/
    POST   /merchants/me/products/<id>/test-sale/
    GET    /merchants/me/keys/
    POST   /merchants/me/keys/rotate/
    POST   /merchants/me/keys/toggle-mode/
    GET    /merchants/me/webhook-logs/
    POST   /merchants/me/webhook-logs/<id>/retry/

  ADMIN (staff only)
    GET    /merchants/admin/
    GET    /merchants/admin/<id>/
    PATCH  /merchants/admin/<id>/
    GET    /merchants/admin/sales/
"""

import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.core.permissions import IsActiveUser
from apps.payments.models import Payment
from apps.payments.payram_client import PayRamError, payram

from .models import (
    CustomerCheckout,
    Merchant,
    MerchantAPIKey,
    WebhookDeliveryLog,
    PostPaymentAction,
    Product,
)
from .serializers import (
    AdminMerchantSerializer,
    CustomerCheckoutDetailSerializer,
    CustomerCheckoutSerializer,
    MerchantAPIKeySerializer,
    MerchantAPIKeyCreatedSerializer,
    MerchantAnalyticsSerializer,
    MerchantCreateSerializer,
    MerchantSerializer,
    MerchantUpdateSerializer,
    PostPaymentActionSerializer,
    ProductCreateSerializer,
    ProductPublicSerializer,
    ProductSerializer,
    RotateKeySerializer,
    RotateKeyResponseSerializer,
    ToggleModeSerializer,
    WebhookDeliveryLogSerializer,
)
from .tasks import trigger_post_payment_actions

logger = logging.getLogger("apps.merchants")


def get_client_ip(request) -> str:
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


# ══════════════════════════════════════════════════════════════════════════════
# THROTTLES
# ══════════════════════════════════════════════════════════════════════════════

class CheckoutRateThrottle(AnonRateThrottle):
    """5 checkout submissions per minute per IP."""
    rate = "5/minute"
    scope = "checkout"


class KeyRotationThrottle(UserRateThrottle):
    """3 key rotations per hour — prevents abuse."""
    rate = "3/hour"
    scope = "key_rotation"


# ══════════════════════════════════════════════════════════════════════════════
# PERMISSIONS
# ══════════════════════════════════════════════════════════════════════════════

class IsMerchantOwner(permissions.BasePermission):
    """Request user must own the Merchant object being accessed."""

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and hasattr(request.user, "merchant_profile")
        )

    def has_object_permission(self, request, view, obj):
        if isinstance(obj, Merchant):
            return obj.user == request.user
        if isinstance(obj, Product):
            return obj.merchant.user == request.user
        if isinstance(obj, PostPaymentAction):
            return obj.product.merchant.user == request.user
        if isinstance(obj, CustomerCheckout):
            return obj.product.merchant.user == request.user
        if isinstance(obj, WebhookDeliveryLog):
            return obj.merchant.user == request.user
        return False


# ══════════════════════════════════════════════════════════════════════════════
# TEST MODE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _resolve_test_mode(request, merchant: Merchant) -> bool:
    """
    Determine if this request should run in test mode.

    Priority order:
      1. ?mode=test in query string (explicit override)
      2. Authorization header contains a test secret key (cs_test_sk_...)
      3. Merchant's is_test_mode setting on their API keys
    """
    if request.GET.get("mode") == "test":
        return True

    auth = request.headers.get("Authorization", "")
    if "cs_test_" in auth:
        return True

    try:
        return merchant.api_keys.is_test_mode
    except MerchantAPIKey.DoesNotExist:
        return True  # safe default — never accidentally go live


def _build_checkout_response(
    checkout: CustomerCheckout,
    product: Product,
    merchant: Merchant,
    payment: Payment | None,
    payram_url: str | None,
    is_test: bool,
) -> dict:
    """
    Build the unified checkout response shape for both test and live mode.
    Frontend relies on this exact shape.
    """
    amount = checkout.amount_usd
    commission_rate = merchant.get_effective_commission_rate()
    commission = (amount * commission_rate).quantize(Decimal("0.01"))
    payout = amount - commission
    settlement_wallet = merchant.get_effective_settlement_wallet() or ""

    return {
        "checkout_id": str(checkout.id),
        "payment_id": str(payment.id) if payment else None,
        "payram_payment_url": payram_url,
        "amount_usd": str(amount),
        "commission_usd": str(payment.commission_usd if payment else commission),
        "payout_usd_equivalent": str(payment.payout_usd_equivalent if payment else payout),
        "product_name": product.name,
        "merchant_name": merchant.business_name,
        "destination_wallet": settlement_wallet,
        "blockchain_code": merchant.settlement_blockchain,
        "currency_code": merchant.settlement_currency,
        "is_test_mode": is_test,
    }


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC VIEWS — no authentication required
# ══════════════════════════════════════════════════════════════════════════════

class MerchantLandingView(APIView):
    """GET /pay/<merchant_slug>/"""

    permission_classes = [permissions.AllowAny]

    def get(self, request, merchant_slug):
        merchant = get_object_or_404(Merchant, slug=merchant_slug, is_active=True)
        products = merchant.products.filter(is_active=True).order_by("created_at")

        is_test = _resolve_test_mode(request, merchant)

        return Response({
            "merchant": {
                "business_name": merchant.business_name,
                "slug": merchant.slug,
                "description": merchant.description,
                "logo_url": merchant.logo_url,
                "is_test_mode": is_test,
            },
            "products": ProductPublicSerializer(products, many=True).data,
        })


class ProductCheckoutPageView(APIView):
    """GET /pay/<merchant_slug>/<product_slug>/"""

    permission_classes = [permissions.AllowAny]

    def get(self, request, merchant_slug, product_slug):
        merchant = get_object_or_404(Merchant, slug=merchant_slug, is_active=True)
        product = get_object_or_404(
            Product, merchant=merchant, slug=product_slug, is_active=True
        )

        if product.is_sold_out:
            return Response(
                {"detail": "This product is sold out."},
                status=status.HTTP_410_GONE,
            )

        data = ProductPublicSerializer(product).data
        data["is_test_mode"] = _resolve_test_mode(request, merchant)
        return Response(data)


class SubmitCheckoutView(APIView):
    """
    POST /pay/<merchant_slug>/<product_slug>/checkout/

    Unified endpoint for both test and live checkouts.

    Test mode:  skips PayRam entirely, creates a synthetic session.
    Live mode:  creates real PayRam session, returns payram_payment_url
                for the frontend iframe. Buyer never sees PayRam domain.

    Response shape (identical for test and live — frontend treats them the same):
        {
            "checkout_id":          "uuid",
            "payment_id":           "uuid | null",
            "payram_payment_url":   "https://... | null",
            "amount_usd":           "100.00",
            "commission_usd":       "30.00",
            "payout_usd_equivalent":"70.00",
            "product_name":         "...",
            "merchant_name":        "...",
            "destination_wallet":   "T...",
            "blockchain_code":      "TRX",
            "currency_code":        "USDT",
            "is_test_mode":         false,
        }
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [CheckoutRateThrottle]

    def post(self, request, merchant_slug, product_slug):
        merchant = get_object_or_404(Merchant, slug=merchant_slug, is_active=True)
        is_test = _resolve_test_mode(request, merchant)

        product = get_object_or_404(
            Product, merchant=merchant, slug=product_slug, is_active=True
        )

        if product.is_sold_out:
            return Response(
                {"detail": "This product is sold out."},
                status=status.HTTP_410_GONE,
            )

        serializer = CustomerCheckoutSerializer(
            data=request.data,
            context={"request": request, "product": product, "is_test": is_test},
        )
        serializer.is_valid(raise_exception=True)
        checkout = serializer.save()

        # ── TEST MODE ─────────────────────────────────────────────────────────
        if is_test:
            checkout.status = CustomerCheckout.Status.PAYMENT_CREATED
            checkout.save(update_fields=["status"])

            response_data = _build_checkout_response(
                checkout=checkout,
                product=product,
                merchant=merchant,
                payment=None,
                payram_url=None,
                is_test=True,
            )
            logger.info(
                "[TEST] Checkout created | merchant=%s | product=%s | email=%s | amount=$%.2f",
                merchant.slug, product.slug, checkout.email, checkout.amount_usd,
            )
            return Response(response_data, status=status.HTTP_201_CREATED)

        # ── LIVE MODE ─────────────────────────────────────────────────────────
        settlement_wallet = merchant.get_effective_settlement_wallet()
        if not settlement_wallet:
            logger.error(
                "Merchant %s has no settlement wallet configured", merchant.slug
            )
            checkout.status = CustomerCheckout.Status.ABANDONED
            checkout.save(update_fields=["status"])
            return Response(
                {"detail": "This merchant cannot accept payments at this time. Please contact them directly."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        guest_user = self._get_or_create_guest_user(merchant)

        payment = Payment(
            user=guest_user,
            merchant=merchant,
            amount_usd=checkout.amount_usd,
            blockchain_code=merchant.settlement_blockchain,
            currency_code=merchant.settlement_currency,
            destination_wallet=settlement_wallet,
            status=Payment.Status.PENDING,
        )
        payment.calculate_commission()
        payment.save()

        checkout.payment = payment
        checkout.status = CustomerCheckout.Status.PAYMENT_CREATED
        checkout.save(update_fields=["payment", "status"])

        try:
            result = payram.initiate_payment(
                customer_email=checkout.email,
                customer_id=str(checkout.id),
                amount_in_usd=checkout.amount_usd,
            )

            payment.payram_reference_id = result["reference_id"]
            payment.payram_payment_url = result["url"]
            payment.status = Payment.Status.OPEN
            payment.save(update_fields=[
                "payram_reference_id", "payram_payment_url", "status"
            ])

            logger.info(
                "[LIVE] Checkout created | merchant=%s | product=%s | email=%s | amount=$%.2f | ref=%s",
                merchant.slug, product.slug, checkout.email,
                checkout.amount_usd, result["reference_id"],
            )

            return Response(
                _build_checkout_response(
                    checkout=checkout,
                    product=product,
                    merchant=merchant,
                    payment=payment,
                    payram_url=result["url"],
                    is_test=False,
                ),
                status=status.HTTP_201_CREATED,
            )

        except PayRamError as exc:
            logger.error(
                "PayRam error | merchant=%s | error=%s", merchant.slug, exc
            )
            payment.status = Payment.Status.FAILED
            payment.error_message = str(exc)
            payment.save(update_fields=["status", "error_message"])
            checkout.status = CustomerCheckout.Status.ABANDONED
            checkout.save(update_fields=["status"])
            return Response(
                {"detail": "Payment system unavailable. Please try again shortly."},
                status=status.HTTP_502_BAD_GATEWAY,
            )

    @staticmethod
    def _get_or_create_guest_user(merchant: Merchant):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        email = f"guest+{merchant.slug}@cashspace.internal"
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "first_name": "Guest",
                "last_name": merchant.business_name,
                "is_active": True,
                "is_email_verified": True,
            }
        )
        if created:
            user.set_unusable_password()
            user.save(update_fields=["password"])
            logger.info("Created guest user for merchant %s", merchant.slug)
        return user


class CheckoutStatusView(APIView):
    """
    GET /pay/<merchant_slug>/<product_slug>/checkout/<checkout_id>/status/
    Buyer polls this. No auth — checkout_id acts as the access token.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, merchant_slug, product_slug, checkout_id):
        checkout = get_object_or_404(
            CustomerCheckout,
            id=checkout_id,
            product__slug=product_slug,
            product__merchant__slug=merchant_slug,
        )

        payment = checkout.payment
        return Response({
            "checkout_id": str(checkout.id),
            "status": checkout.status,
            "payment_status": payment.status if payment else "NOT_CREATED",
            "payout_status": payment.payout_status if payment else "—",
            "automation_triggered": checkout.automation_triggered,
            "is_test": checkout.is_test,
            "success_redirect_url": checkout.product.success_redirect_url or None,
        })


class TestCompleteView(APIView):
    """
    POST /pay/<merchant_slug>/<product_slug>/checkout/<checkout_id>/test-complete/

    Test mode only. Marks a checkout as completed without real payment.
    Called by the frontend "Simulate payment" button.
    Fires post-payment automations.
    Returns 403 in live mode.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, merchant_slug, product_slug, checkout_id):
        merchant = get_object_or_404(Merchant, slug=merchant_slug, is_active=True)

        if not _resolve_test_mode(request, merchant):
            return Response(
                {"detail": "This endpoint is only available in test mode."},
                status=status.HTTP_403_FORBIDDEN,
            )

        checkout = get_object_or_404(
            CustomerCheckout,
            id=checkout_id,
            product__slug=product_slug,
            product__merchant__slug=merchant_slug,
            is_test=True,
        )

        if checkout.status == CustomerCheckout.Status.COMPLETED:
            return Response({
                "checkout_id": str(checkout.id),
                "status": "completed",
                "message": "Already completed.",
            })

        checkout.status = CustomerCheckout.Status.COMPLETED
        checkout.automation_triggered = True
        checkout.automation_triggered_at = timezone.now()
        checkout.save(update_fields=[
            "status", "automation_triggered", "automation_triggered_at"
        ])

        logger.info(
            "[TEST] Checkout completed | checkout=%s | merchant=%s | buyer=%s",
            checkout_id, merchant_slug, checkout.email,
        )

        return Response({
            "checkout_id": str(checkout.id),
            "status": "completed",
            "message": "Test payment completed successfully.",
            "automation_triggered": True,
        })


# ══════════════════════════════════════════════════════════════════════════════
# MERCHANT DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

class MerchantRegisterView(generics.CreateAPIView):
    """
    POST /merchants/register/

    Creates merchant + auto-generates API keypairs via signal.
    Returns the full raw secret keys ONCE in the response.
    Frontend must show a "Save these — you won't see them again" warning.
    """

    serializer_class = MerchantCreateSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        merchant = serializer.save()

        # Retrieve the keys that were auto-created by the signal.
        # We need to rotate once to get the raw values back out since
        # the signal only stores hashes.
        try:
            api_keys = merchant.api_keys
            test_sk = api_keys.rotate_key("test")
            live_sk = api_keys.rotate_key("live")
        except MerchantAPIKey.DoesNotExist:
            # Fallback: create manually if signal didn't fire
            api_keys, test_sk, live_sk = MerchantAPIKey.create_for_merchant(merchant)

        logger.info(
            "New merchant registered: %s (user=%s)", merchant.slug, request.user.email
        )

        merchant_data = MerchantSerializer(merchant).data
        merchant_data["_keys_shown_once"] = {
            "test_publishable_key": api_keys.test_publishable_key,
            "test_secret_key": test_sk,
            "live_publishable_key": api_keys.live_publishable_key,
            "live_secret_key": live_sk,
            "warning": "Save these secret keys now. They will not be shown again.",
        }

        return Response(merchant_data, status=status.HTTP_201_CREATED)


class MerchantMeView(generics.RetrieveUpdateAPIView):
    """GET /merchants/me/ | PATCH /merchants/me/"""

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return MerchantUpdateSerializer
        return MerchantSerializer

    def get_object(self):
        return get_object_or_404(Merchant, user=self.request.user)


# ── API Key Management ────────────────────────────────────────────────────────

class MerchantAPIKeysView(APIView):
    """
    GET /merchants/me/keys/
    Returns the safe (non-secret) view of the merchant's API keys.
    Secret keys are never returned — only the prefix for display.
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def get(self, request):
        merchant = get_object_or_404(Merchant, user=request.user)
        api_keys = get_object_or_404(MerchantAPIKey, merchant=merchant)
        return Response(MerchantAPIKeySerializer(api_keys).data)


class RotateAPIKeyView(APIView):
    """
    POST /merchants/me/keys/rotate/

    Rotates the secret key for the specified environment (test or live).
    The old key is immediately invalidated.
    The new raw secret key is returned ONCE — never retrievable again.

    Request body: { "env": "test" | "live" }
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]
    throttle_classes = [KeyRotationThrottle]

    def post(self, request):
        serializer = RotateKeySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        env = serializer.validated_data["env"]

        merchant = get_object_or_404(Merchant, user=request.user)
        api_keys = get_object_or_404(MerchantAPIKey, merchant=merchant)

        new_secret_key = api_keys.rotate_key(env)
        rotated_at = (
            api_keys.test_key_rotated_at
            if env == "test"
            else api_keys.live_key_rotated_at
        )

        logger.info(
            "API key rotated | merchant=%s | env=%s | user=%s",
            merchant.slug, env, request.user.email,
        )

        return Response({
            "env": env,
            "new_secret_key": new_secret_key,
            "rotated_at": rotated_at,
            "warning": "Save this key now. It will not be shown again.",
        })


class ToggleModeView(APIView):
    """
    POST /merchants/me/keys/toggle-mode/

    Switch between test and live mode.
    Request body: { "mode": "test" | "live" }

    Switching to live mode requires:
      - Merchant is verified (is_verified=True)
      - Settlement wallet is configured

    Returns the updated API key state.
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def post(self, request):
        serializer = ToggleModeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mode = serializer.validated_data["mode"]

        merchant = get_object_or_404(Merchant, user=request.user)
        api_keys = get_object_or_404(MerchantAPIKey, merchant=merchant)

        going_live = mode == "live"

        # Guard: cannot go live without verification + wallet
        if going_live:
            errors = []
            if not merchant.is_verified:
                errors.append("Your account must be verified before enabling live mode. Contact support.")
            if not merchant.get_effective_settlement_wallet():
                errors.append("You must configure a settlement wallet before enabling live mode.")
            if errors:
                return Response(
                    {"detail": errors},
                    status=status.HTTP_403_FORBIDDEN,
                )

        api_keys.is_test_mode = not going_live
        api_keys.save(update_fields=["is_test_mode"])

        logger.info(
            "Mode toggled | merchant=%s | mode=%s | user=%s",
            merchant.slug, mode, request.user.email,
        )

        return Response({
            "mode": mode,
            "is_test_mode": api_keys.is_test_mode,
            "message": f"Switched to {'test' if api_keys.is_test_mode else 'live'} mode.",
        })


# ── Analytics ─────────────────────────────────────────────────────────────────

class MerchantAnalyticsView(APIView):
    """
    GET /merchants/me/analytics/?period=30d

    Returns revenue, sales volume, conversion rate, daily breakdown,
    and top products. Only counts live (non-test) transactions.

    Query params:
        period: "7d" | "30d" | "90d" | "1y"  (default: 30d)
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    PERIOD_DAYS = {"7d": 7, "30d": 30, "90d": 90, "1y": 365}

    def get(self, request):
        merchant = get_object_or_404(Merchant, user=request.user)
        period = request.GET.get("period", "30d")
        days = self.PERIOD_DAYS.get(period, 30)

        since = timezone.now() - timedelta(days=days)

        base_qs = CustomerCheckout.objects.filter(
            product__merchant=merchant,
            is_test=False,
            created_at__gte=since,
        )

        completed_qs = base_qs.filter(status=CustomerCheckout.Status.COMPLETED)

        # Totals
        total_checkouts = base_qs.count()
        total_sales = completed_qs.count()
        revenue_result = completed_qs.aggregate(total=Sum("amount_usd"))
        total_revenue = revenue_result["total"] or Decimal("0.00")
        conversion_rate = (
            round((total_sales / total_checkouts) * 100, 1)
            if total_checkouts > 0 else 0.0
        )

        # Daily revenue breakdown
        daily = (
            completed_qs
            .annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(revenue=Sum("amount_usd"), sales=Count("id"))
            .order_by("day")
        )
        daily_revenue = [
            {
                "date": str(row["day"]),
                "revenue": str(row["revenue"] or Decimal("0.00")),
                "sales": row["sales"],
            }
            for row in daily
        ]

        # Top products by revenue
        top_products = (
            completed_qs
            .values("product__id", "product__name")
            .annotate(revenue=Sum("amount_usd"), sales=Count("id"))
            .order_by("-revenue")[:5]
        )
        top_products_data = [
            {
                "product_id": str(row["product__id"]),
                "product_name": row["product__name"],
                "revenue": str(row["revenue"] or Decimal("0.00")),
                "sales": row["sales"],
            }
            for row in top_products
        ]

        return Response({
            "period": period,
            "total_revenue_usd": str(total_revenue),
            "total_sales": total_sales,
            "total_checkouts": total_checkouts,
            "conversion_rate_pct": conversion_rate,
            "daily_revenue": daily_revenue,
            "top_products": top_products_data,
        })


# ── Sales CRM ─────────────────────────────────────────────────────────────────

class MerchantSalesListView(generics.ListAPIView):
    """GET /merchants/me/sales/"""

    serializer_class = CustomerCheckoutDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]
    filterset_fields = ["status", "product", "automation_triggered", "is_test"]
    search_fields = ["email", "full_name", "telegram_username", "discord_username"]
    ordering_fields = ["created_at", "amount_usd", "status"]

    def get_queryset(self):
        merchant = get_object_or_404(Merchant, user=self.request.user)
        return (
            CustomerCheckout.objects
            .filter(product__merchant=merchant)
            .select_related("product", "payment")
            .order_by("-created_at")
        )


class MerchantSaleDetailView(generics.RetrieveAPIView):
    """GET /merchants/me/sales/<id>/"""

    serializer_class = CustomerCheckoutDetailSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def get_object(self):
        merchant = get_object_or_404(Merchant, user=self.request.user)
        return get_object_or_404(
            CustomerCheckout,
            id=self.kwargs["pk"],
            product__merchant=merchant,
        )


class RetriggerAutomationView(APIView):
    """POST /merchants/me/sales/<id>/retrigger/"""

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def post(self, request, pk):
        merchant = get_object_or_404(Merchant, user=request.user)
        checkout = get_object_or_404(
            CustomerCheckout,
            id=pk,
            product__merchant=merchant,
            status=CustomerCheckout.Status.COMPLETED,
        )

        checkout.automation_triggered = False
        checkout.automation_error = ""
        checkout.save(update_fields=["automation_triggered", "automation_error"])

        trigger_post_payment_actions.delay(str(checkout.id))

        logger.info(
            "Automation retriggered | merchant=%s | checkout=%s | buyer=%s",
            merchant.slug, checkout.id, checkout.email,
        )
        return Response({"detail": "Automation re-queued successfully."})


# ── Products ──────────────────────────────────────────────────────────────────

class MerchantProductListView(generics.ListCreateAPIView):
    """GET /merchants/me/products/ | POST /merchants/me/products/"""

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ProductCreateSerializer
        return ProductSerializer

    def get_queryset(self):
        merchant = get_object_or_404(Merchant, user=self.request.user)
        return Product.objects.filter(merchant=merchant).prefetch_related(
            "post_payment_actions"
        ).order_by("created_at")

    def perform_create(self, serializer):
        merchant = get_object_or_404(Merchant, user=self.request.user)
        serializer.save(merchant=merchant)
        logger.info(
            "Product created | merchant=%s | product=%s",
            merchant.slug, serializer.instance.slug,
        )


class MerchantProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PATCH / DELETE /merchants/me/products/<id>/"""

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return ProductCreateSerializer
        return ProductSerializer

    def get_queryset(self):
        merchant = get_object_or_404(Merchant, user=self.request.user)
        return Product.objects.filter(merchant=merchant)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        logger.info(
            "Product deactivated | merchant=%s | product=%s",
            instance.merchant.slug, instance.slug,
        )


# ── Post-Payment Actions ──────────────────────────────────────────────────────

class MerchantActionListView(generics.ListCreateAPIView):
    """GET / POST /merchants/me/products/<product_id>/actions/"""

    serializer_class = PostPaymentActionSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def _get_product(self):
        merchant = get_object_or_404(Merchant, user=self.request.user)
        return get_object_or_404(Product, id=self.kwargs["product_id"], merchant=merchant)

    def get_queryset(self):
        return PostPaymentAction.objects.filter(
            product=self._get_product()
        ).order_by("priority")

    def perform_create(self, serializer):
        serializer.save(product=self._get_product())


class MerchantActionDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PATCH / DELETE /merchants/me/products/<product_id>/actions/<pk>/"""

    serializer_class = PostPaymentActionSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def get_queryset(self):
        merchant = get_object_or_404(Merchant, user=self.request.user)
        product = get_object_or_404(
            Product, id=self.kwargs["product_id"], merchant=merchant
        )
        return PostPaymentAction.objects.filter(product=product)


# ── Test Sale ─────────────────────────────────────────────────────────────────

class TestSaleView(APIView):
    """
    POST /merchants/me/products/<product_id>/test-sale/

    Simulates a complete sale without real payment.
    Creates a realistic CustomerCheckout with is_test=True, status=completed,
    and fires post-payment automations.

    Used from the merchant dashboard to verify automation setup before going live.
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def post(self, request, product_id):
        merchant = get_object_or_404(Merchant, user=request.user)
        product = get_object_or_404(Product, id=product_id, merchant=merchant)

        price = product.price_usd or product.min_price_usd or Decimal("10.00")

        checkout = CustomerCheckout.objects.create(
            product=product,
            email=f"test+{secrets.token_hex(4)}@cashspace.test",
            full_name="Test Buyer",
            telegram_username="testbuyer" if product.collect_telegram else "",
            discord_username="testbuyer#0000" if product.collect_discord else "",
            phone_number="+15550000000" if product.collect_phone else "",
            custom_field_value="TEST_VALUE" if product.collect_custom_field else "",
            amount_usd=price,
            is_test=True,
            status=CustomerCheckout.Status.COMPLETED,
            automation_triggered=False,
            metadata={"source": "test_sale", "created_by": str(request.user.id)},
        )

        trigger_post_payment_actions.delay(str(checkout.id))

        logger.info(
            "[TEST] Test sale created | merchant=%s | product=%s | checkout=%s",
            merchant.slug, product.slug, checkout.id,
        )

        return Response(
            CustomerCheckoutDetailSerializer(checkout).data,
            status=status.HTTP_201_CREATED,
        )


# ── Webhook Delivery Logs ─────────────────────────────────────────────────────

class WebhookDeliveryLogListView(generics.ListAPIView):
    """
    GET /merchants/me/webhook-logs/

    All webhook delivery attempts for this merchant.
    Supports filtering by status, event_type, is_test.
    """

    serializer_class = WebhookDeliveryLogSerializer
    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]
    filterset_fields = ["status", "event_type", "is_test"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        merchant = get_object_or_404(Merchant, user=self.request.user)
        return (
            WebhookDeliveryLog.objects
            .filter(merchant=merchant)
            .select_related("checkout")
            .order_by("-created_at")
        )


class WebhookDeliveryLogRetryView(APIView):
    """
    POST /merchants/me/webhook-logs/<id>/retry/

    Manually retrigger a failed webhook delivery.
    Only available for logs with status=failed and attempt_number < MAX_ATTEMPTS.
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsMerchantOwner]

    def post(self, request, pk):
        merchant = get_object_or_404(Merchant, user=request.user)
        log = get_object_or_404(
            WebhookDeliveryLog,
            id=pk,
            merchant=merchant,
        )

        if not log.can_retry:
            return Response(
                {
                    "detail": (
                        "This webhook cannot be retried. "
                        f"Status: {log.status}, attempts: {log.attempt_number}/{log.MAX_ATTEMPTS}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Re-queue via Celery
        from .tasks import retry_webhook_delivery
        retry_webhook_delivery.delay(str(log.id))

        logger.info(
            "Webhook retry queued | merchant=%s | log=%s | attempt=%d",
            merchant.slug, log.id, log.attempt_number + 1,
        )

        return Response({"detail": "Webhook retry queued."})


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN VIEWS
# ══════════════════════════════════════════════════════════════════════════════

class AdminMerchantListView(generics.ListAPIView):
    """GET /merchants/admin/"""

    serializer_class = AdminMerchantSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    search_fields = ["business_name", "slug", "user__email"]
    filterset_fields = ["is_active", "is_verified"]
    ordering_fields = ["created_at", "business_name"]

    def get_queryset(self):
        return Merchant.objects.select_related("user").order_by("-created_at")


class AdminMerchantDetailView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /merchants/admin/<id>/"""

    serializer_class = AdminMerchantSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    queryset = Merchant.objects.select_related("user").prefetch_related("products")


class AdminAllSalesView(generics.ListAPIView):
    """GET /merchants/admin/sales/"""

    serializer_class = CustomerCheckoutDetailSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filterset_fields = ["status", "automation_triggered", "is_test"]
    search_fields = ["email", "full_name", "telegram_username"]
    ordering_fields = ["created_at", "amount_usd"]

    def get_queryset(self):
        return (
            CustomerCheckout.objects
            .select_related("product", "product__merchant", "payment")
            .order_by("-created_at")
        )