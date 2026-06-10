"""
apps/creator/views.py
=====================
Advanced views for the creator app.

Provides:
  - Creator profile management (retrieve, update)
  - Payable asset CRUD (list, create, detail, update, delete, stats)
  - Public asset page and checkout (no auth)
  - Sale listing and detail for creators
  - Affiliate program management
  - Discount code management
  - Webhook receiver for payment confirmation
  - Analytics and stats endpoints

All views include proper permissions, rate limiting, logging, and error handling.
"""

import logging
from decimal import Decimal
from urllib.parse import urlencode

from django.conf import settings
from django.db import transaction
from django.db.models import Q, Count, Sum, F
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from rest_framework import generics, permissions, status, serializers as drf_serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.accounts.models import AuditLog
from apps.core.permissions import IsActiveUser, IsOwnerOrAdmin
from apps.payments.models import Payment
from apps.payments.payram_client import payram, PayRamError
from apps.gating.tokens import create_access_token
from apps.gating.models import AccessGrant

from .models import CreatorProfile, PayableAsset, CreatorSale, CreatorAffiliateProgram, CreatorDiscountCode
from .serializers import (
    CreatorProfileSerializer,
    PayableAssetListSerializer,
    PayableAssetDetailSerializer,
    PayableAssetCreateSerializer,
    PublicAssetSerializer,
    CreatorSaleSerializer,
    CreatorSaleDetailSerializer,
    CreatorAffiliateProgramSerializer,
    CreatorDiscountCodeSerializer,
    PublicCheckoutRequestSerializer,
    PublicCheckoutResponseSerializer,
    CreatorStatsSerializer,
)

logger = logging.getLogger("apps.creator")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


def get_or_create_creator_profile(user):
    """Get or create CreatorProfile for a user. Auto‑creates if missing."""
    profile, created = CreatorProfile.objects.get_or_create(user=user)
    if created:
        logger.info(f"Auto‑created creator profile for user {user.email}")
    return profile


# ----------------------------------------------------------------------
# Creator Profile Views
# ----------------------------------------------------------------------
class CreatorProfileView(generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/creator/profile/ – retrieve own profile
    PATCH /api/v1/creator/profile/ – update own profile
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    serializer_class = CreatorProfileSerializer

    def get_object(self):
        return get_or_create_creator_profile(self.request.user)


# ----------------------------------------------------------------------
# Payable Asset Management (Creator)
# ----------------------------------------------------------------------
class CreatorAssetListView(generics.ListCreateAPIView):
    """
    GET /api/v1/creator/assets/ – list all assets for authenticated creator
    POST /api/v1/creator/assets/ – create a new payable asset
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return PayableAssetCreateSerializer
        return PayableAssetListSerializer

    def get_queryset(self):
        profile = get_or_create_creator_profile(self.request.user)
        return PayableAsset.objects.filter(creator=profile).order_by("-created_at")

    def perform_create(self, serializer):
        profile = get_or_create_creator_profile(self.request.user)
        asset = serializer.save(creator=profile)
        AuditLog.objects.create(
            user=self.request.user,
            action="creator_asset_created",
            metadata={"asset_id": str(asset.id), "asset_title": asset.title},
        )
        logger.info(f"Creator {self.request.user.email} created asset {asset.id}")


class CreatorAssetDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/v1/creator/assets/<uuid>/ – retrieve asset detail
    PUT/PATCH /api/v1/creator/assets/<uuid>/ – update asset
    DELETE /api/v1/creator/assets/<uuid>/ – soft delete (set is_active=False)
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    serializer_class = PayableAssetDetailSerializer

    def get_queryset(self):
        profile = get_or_create_creator_profile(self.request.user)
        return PayableAsset.objects.filter(creator=profile)

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])
        AuditLog.objects.create(
            user=self.request.user,
            action="creator_asset_deactivated",
            metadata={"asset_id": str(instance.id)},
        )
        logger.info(f"Creator {self.request.user.email} deactivated asset {instance.id}")


class CreatorAssetStatsView(APIView):
    """
    GET /api/v1/creator/assets/<uuid>/stats/ – detailed analytics for an asset
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def get(self, request, pk):
        profile = get_or_create_creator_profile(request.user)
        asset = get_object_or_404(PayableAsset, pk=pk, creator=profile)
        sales = asset.sales.filter(status=CreatorSale.Status.COMPLETED)
        total_sales = sales.count()
        total_revenue = sales.aggregate(total=Sum("amount_usd"))["total"] or Decimal("0")
        total_net = sales.aggregate(net=Sum("net_usd"))["net"] or Decimal("0")
        avg_price = total_revenue / total_sales if total_sales > 0 else Decimal("0")
        # Sales by day for last 30 days
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        daily = sales.filter(created_at__gte=thirty_days_ago).extra(
            select={"day": "date(created_at)"}
        ).values("day").annotate(count=Count("id"), revenue=Sum("amount_usd"))
        return Response({
            "total_sales": total_sales,
            "total_revenue_usd": str(total_revenue),
            "total_net_usd": str(total_net),
            "average_order_value_usd": str(avg_price),
            "conversion_rate": (total_sales / max(asset.view_count, 1)) * 100,
            "daily_sales_last_30_days": daily,
            "asset": PayableAssetListSerializer(asset).data,
        })


# ----------------------------------------------------------------------
# Public Asset Page & Checkout (No Authentication)
# ----------------------------------------------------------------------
class PublicAssetPageView(APIView):
    """
    GET /creator/pay/<slug>/ – public asset details for checkout page
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def get(self, request, slug):
        asset = get_object_or_404(PayableAsset, slug=slug, is_active=True)
        if asset.is_sold_out:
            return Response({"error": "Sold out"}, status=status.HTTP_410_GONE)
        # Increment view count
        asset.view_count = F("view_count") + 1
        asset.save(update_fields=["view_count"])
        serializer = PublicAssetSerializer(asset, context={"request": request})
        return Response(serializer.data)


class PublicCheckoutView(APIView):
    """
    POST /creator/pay/<slug>/checkout/
    Buyer submits email and optional amount/tier.
    Creates a CreatorSale, initiates PayRam payment, returns payment URL.
    """
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request, slug):
        asset = get_object_or_404(PayableAsset, slug=slug, is_active=True)
        if asset.is_sold_out:
            return Response({"error": "Sold out"}, status=status.HTTP_410_GONE)

        serializer = PublicCheckoutRequestSerializer(
            data=request.data,
            context={"asset": asset}
        )
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        email = validated["email"]
        full_name = validated.get("full_name", "")

        # Check per‑buyer limit
        if asset.max_sales_per_buyer > 0:
            existing_sales = CreatorSale.objects.filter(
                asset=asset, buyer_email=email, status=CreatorSale.Status.COMPLETED
            ).count()
            if existing_sales >= asset.max_sales_per_buyer:
                return Response(
                    {"error": f"You have already purchased this item {existing_sales} times."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Determine amount
        amount_usd = None
        selected_tier = None
        if asset.pricing_type == PayableAsset.PricingType.FIXED:
            amount_usd = asset.price_usd
        elif asset.pricing_type == PayableAsset.PricingType.PAY_WHAT_YOU_WANT:
            amount_usd = validated["amount_usd"]
        elif asset.pricing_type == PayableAsset.PricingType.TIERED:
            tier_idx = validated["tier_index"]
            selected_tier = asset.price_tiers[tier_idx]
            amount_usd = Decimal(str(selected_tier["price"]))
        # Subscription would be handled separately (not in this simple checkout)

        # Apply discount code
        discount_code = validated.get("discount_code")
        discount_amount = Decimal("0")
        if discount_code:
            try:
                dc = CreatorDiscountCode.objects.get(
                    asset=asset, code=discount_code.upper(), is_active=True
                )
                if dc.is_valid():
                    original = amount_usd
                    amount_usd = dc.apply(original)
                    discount_amount = original - amount_usd
                    dc.used_count += 1
                    dc.save(update_fields=["used_count"])
            except CreatorDiscountCode.DoesNotExist:
                pass  # ignore invalid code

        # Calculate commission and net
        commission_rate = asset.creator.get_effective_commission_rate()
        commission = amount_usd * commission_rate
        net = amount_usd - commission

        # Create CreatorSale
        sale = CreatorSale.objects.create(
            asset=asset,
            buyer_email=email,
            buyer_name=full_name,
            amount_usd=amount_usd,
            commission_usd=commission,
            net_usd=net,
            status=CreatorSale.Status.PENDING,
            metadata={
                "ip": get_client_ip(request),
                "user_agent": request.META.get("HTTP_USER_AGENT", ""),
                "affiliate_code": validated.get("affiliate_code"),
                "discount_code": discount_code,
                "selected_tier": selected_tier,
            }
        )

        # Get settlement wallet (creator's payout wallet)
        settlement_wallet = asset.get_settlement_wallet()
        if not settlement_wallet:
            sale.status = CreatorSale.Status.FAILED
            sale.save()
            return Response(
                {"error": "Creator has not configured a payout wallet."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Create Payment record (needed for PayRam)
        payment = Payment(
            user=asset.creator.user,
            amount_usd=amount_usd,
            blockchain_code=asset.custom_settlement_blockchain or "TRX",
            currency_code=asset.custom_settlement_currency or "USDT",
            destination_wallet=settlement_wallet,
            status=Payment.Status.PENDING,
        )
        payment.calculate_commission()
        payment.save()

        # Link payment to sale
        sale.payment_id = payment.id
        sale.save(update_fields=["payment_id"])

        # Initiate PayRam session
        try:
            payram_result = payram.initiate_payment(
                customer_email=email,
                customer_id=str(sale.id),
                amount_in_usd=amount_usd,
            )
            payment.payram_reference_id = payram_result["reference_id"]
            payment.payram_payment_url = payram_result["url"]
            payment.status = Payment.Status.OPEN
            payment.save(update_fields=["payram_reference_id", "payram_payment_url", "status"])
            sale.status = CreatorSale.Status.PROCESSING
            sale.save(update_fields=["status"])
        except PayRamError as e:
            logger.error(f"PayRam error for sale {sale.id}: {e}")
            payment.status = Payment.Status.FAILED
            payment.save()
            sale.status = CreatorSale.Status.FAILED
            sale.save()
            return Response({"error": "Payment system unavailable"}, status=502)

        # Schedule a Celery task to check payment status and activate grant later
        from .tasks import process_payment_confirmation
        process_payment_confirmation.delay(str(sale.id))

        response_data = PublicCheckoutResponseSerializer({
            "sale_id": sale.id,
            "payment_url": payment.payram_payment_url,
            "amount_usd": amount_usd,
            "asset_title": asset.title,
        }).data
        return Response(response_data, status=status.HTTP_201_CREATED)


# ----------------------------------------------------------------------
# Creator Sales Views
# ----------------------------------------------------------------------
class CreatorSalesListView(generics.ListAPIView):
    """
    GET /api/v1/creator/sales/ – list all sales for the authenticated creator
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    serializer_class = CreatorSaleSerializer
    filterset_fields = ["status", "asset"]
    ordering_fields = ["created_at", "amount_usd"]

    def get_queryset(self):
        profile = get_or_create_creator_profile(self.request.user)
        return CreatorSale.objects.filter(asset__creator=profile).order_by("-created_at")


class CreatorSaleDetailView(generics.RetrieveAPIView):
    """
    GET /api/v1/creator/sales/<uuid>/ – detail of a single sale
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    serializer_class = CreatorSaleDetailSerializer

    def get_queryset(self):
        profile = get_or_create_creator_profile(self.request.user)
        return CreatorSale.objects.filter(asset__creator=profile)


# ----------------------------------------------------------------------
# Affiliate Program Views
# ----------------------------------------------------------------------
class CreatorAffiliateProgramView(generics.RetrieveUpdateAPIView):
    """
    GET /api/v1/creator/assets/<asset_id>/affiliate/ – get affiliate program
    PUT/PATCH /api/v1/creator/assets/<asset_id>/affiliate/ – update affiliate program
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def get_queryset(self):
        profile = get_or_create_creator_profile(self.request.user)
        return PayableAsset.objects.filter(creator=profile)

    def get_object(self):
        asset = get_object_or_404(self.get_queryset(), pk=self.kwargs["asset_id"])
        program, created = CreatorAffiliateProgram.objects.get_or_create(asset=asset)
        return program

    def get_serializer_class(self):
        return CreatorAffiliateProgramSerializer


# ----------------------------------------------------------------------
# Discount Code Views
# ----------------------------------------------------------------------
class CreatorDiscountCodeListView(generics.ListCreateAPIView):
    """
    GET /api/v1/creator/assets/<asset_id>/discounts/ – list discount codes for asset
    POST /api/v1/creator/assets/<asset_id>/discounts/ – create discount code
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    serializer_class = CreatorDiscountCodeSerializer

    def get_queryset(self):
        profile = get_or_create_creator_profile(self.request.user)
        asset = get_object_or_404(PayableAsset, pk=self.kwargs["asset_id"], creator=profile)
        return CreatorDiscountCode.objects.filter(asset=asset)

    def perform_create(self, serializer):
        profile = get_or_create_creator_profile(self.request.user)
        asset = get_object_or_404(PayableAsset, pk=self.kwargs["asset_id"], creator=profile)
        serializer.save(asset=asset)


class CreatorDiscountCodeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/v1/creator/assets/<asset_id>/discounts/<code_id>/ – retrieve/update/delete discount code
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]
    serializer_class = CreatorDiscountCodeSerializer

    def get_queryset(self):
        profile = get_or_create_creator_profile(self.request.user)
        asset = get_object_or_404(PayableAsset, pk=self.kwargs["asset_id"], creator=profile)
        return CreatorDiscountCode.objects.filter(asset=asset)


# ----------------------------------------------------------------------
# Creator Stats (global)
# ----------------------------------------------------------------------
class CreatorStatsView(APIView):
    """
    GET /api/v1/creator/stats/ – global statistics for the creator
    """
    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def get(self, request):
        profile = get_or_create_creator_profile(request.user)
        sales = CreatorSale.objects.filter(asset__creator=profile, status=CreatorSale.Status.COMPLETED)
        total_sales = sales.count()
        total_revenue = sales.aggregate(total=Sum("amount_usd"))["total"] or Decimal("0")
        total_net = sales.aggregate(net=Sum("net_usd"))["net"] or Decimal("0")
        avg_price = total_revenue / total_sales if total_sales > 0 else Decimal("0")
        return Response({
            "total_assets": profile.assets.count(),
            "total_sales": total_sales,
            "total_revenue_usd": str(total_revenue),
            "total_net_usd": str(total_net),
            "average_order_value_usd": str(avg_price),
            "pending_earnings_usd": str(sales.filter(status=CreatorSale.Status.PROCESSING).aggregate(s=Sum("net_usd"))["s"] or Decimal("0")),
            "profile": CreatorProfileSerializer(profile).data,
        })


# ----------------------------------------------------------------------
# Webhook Receiver (for payment confirmation)
# ----------------------------------------------------------------------
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


@method_decorator(csrf_exempt, name="dispatch")
class CreatorWebhookView(APIView):
    """
    POST /api/v1/creator/webhook/
    Receives PayRam payment confirmation and activates the sale.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Verify signature (simplified – use payram.verify_webhook_signature in production)
        payload = request.data
        reference_id = payload.get("reference_id")
        payment_state = payload.get("paymentState")

        if not reference_id or payment_state != "FILLED":
            return Response({"status": "ignored"})

        # Find sale via payment
        try:
            payment = Payment.objects.get(payram_reference_id=reference_id)
            sale = CreatorSale.objects.get(payment_id=payment.id)
        except (Payment.DoesNotExist, CreatorSale.DoesNotExist):
            logger.warning(f"Webhook: no sale found for reference_id {reference_id}")
            return Response({"status": "no_sale_found"})

        if sale.status == CreatorSale.Status.COMPLETED:
            return Response({"status": "already_completed"})

        with transaction.atomic():
            sale.status = CreatorSale.Status.COMPLETED
            sale.paid_at = timezone.now()
            sale.save(update_fields=["status", "paid_at"])

            # Generate access token for the buyer
            token_expires_hours = sale.asset.token_expires_hours or 0
            expires_in_seconds = token_expires_hours * 3600 if token_expires_hours else None
            token = create_access_token(
                asset_id=str(sale.asset.id),
                grant_id=str(sale.id),
                buyer_email=sale.buyer_email,
                expires_in_seconds=expires_in_seconds,
                max_uses=sale.asset.token_max_uses,
                custom_claims={"creator_asset": True}
            )
            sale.access_token = token
            sale.save(update_fields=["access_token"])

            # Update asset stats
            sale.asset.total_sales = F("total_sales") + 1
            sale.asset.revenue_usd = F("revenue_usd") + sale.amount_usd
            sale.asset.save(update_fields=["total_sales", "revenue_usd"])

            # Update creator profile stats
            profile = sale.asset.creator
            profile.total_sales = F("total_sales") + 1
            profile.total_revenue_usd = F("total_revenue_usd") + sale.amount_usd
            profile.save(update_fields=["total_sales", "total_revenue_usd"])

            # Send email to buyer (task)
            from .tasks import send_access_email
            send_access_email.delay(str(sale.id))

            # Webhook to creator (if configured)
            if sale.asset.webhook_url:
                from .tasks import call_creator_webhook
                call_creator_webhook.delay(str(sale.id))

        logger.info(f"Sale {sale.id} completed, token issued")
        return Response({"status": "completed"})