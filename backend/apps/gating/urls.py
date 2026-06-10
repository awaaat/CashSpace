"""
apps/gating/urls.py
===================
URL configuration for the gating app.

Exposes endpoints for:
  - Public asset checkout and purchase
  - Token verification (for external merchants)
  - Proxy streaming of paid content
  - Direct file downloads
  - Embed token generation (for iframes)
  - Grant status polling
  - Asset management (creator/merchant dashboards)

All endpoints are versioned under /api/v1/gating/.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_nested.routers import NestedDefaultRouter  # optional, but we'll use simple paths

# Import views (these will be created in views.py)
from . import views
from .verify import TokenVerifyView, BatchTokenVerifyView, TokenIntrospectView, LegacyTokenVerifyView
from .proxy import ProxyView, DirectFileView

# ----------------------------------------------------------------------
# Router for ViewSets (if we use them)
# ----------------------------------------------------------------------
router = DefaultRouter()
router.register(r"assets", views.GatedAssetViewSet, basename="gated-asset")
router.register(r"grants", views.AccessGrantViewSet, basename="access-grant")
router.register(r"discount-codes", views.DiscountCodeViewSet, basename="discount-code")

# Nested routes for grants under assets
assets_router = NestedDefaultRouter(router, r"assets", lookup="asset")
assets_router.register(r"grants", views.AssetGrantViewSet, basename="asset-grants")

# ----------------------------------------------------------------------
# URL patterns
# ----------------------------------------------------------------------
urlpatterns = [
    # --------------------------------------------------------------
    # Public checkout & purchase (no auth required)
    # --------------------------------------------------------------
    path("assets/<slug:slug>/", views.PublicAssetDetailView.as_view(), name="public-asset-detail"),
    path("assets/<slug:slug>/checkout/", views.PublicCheckoutView.as_view(), name="public-checkout"),
    path("checkout/<uuid:grant_id>/status/", views.CheckoutStatusView.as_view(), name="checkout-status"),

    # --------------------------------------------------------------
    # Access & unlocking
    # --------------------------------------------------------------
    path("unlock/<str:token>/", views.UnlockRedirectView.as_view(), name="unlock-redirect"),
    path("embed/<uuid:token>/", views.EmbedContentView.as_view(), name="embed-content"),

    # --------------------------------------------------------------
    # Token verification (for external servers)
    # --------------------------------------------------------------
    path("verify-token/", TokenVerifyView.as_view(), name="verify-token"),
    path("verify-batch/", BatchTokenVerifyView.as_view(), name="verify-batch"),
    path("introspect/", TokenIntrospectView.as_view(), name="introspect"),
    path("verify-token-legacy/", LegacyTokenVerifyView.as_view(), name="verify-token-legacy"),

    # --------------------------------------------------------------
    # Proxy streaming & direct file download
    # --------------------------------------------------------------
    path("proxy/<str:token>/", ProxyView.as_view(), name="proxy"),
    path("proxy/<str:token>/<path:extra_path>", ProxyView.as_view(), name="proxy-with-path"),
    path("download/<str:token>/", DirectFileView.as_view(), name="direct-download"),

    # --------------------------------------------------------------
    # Grant status (polling)
    # --------------------------------------------------------------
    path("grants/<uuid:grant_id>/status/", views.GrantStatusView.as_view(), name="grant-status"),
    path("grants/<uuid:grant_id>/resend/", views.ResendAccessView.as_view(), name="resend-access"),

    # --------------------------------------------------------------
    # Affiliate endpoint (generate code, track clicks)
    # --------------------------------------------------------------
    path("affiliate/generate/", views.GenerateAffiliateCodeView.as_view(), name="generate-affiliate"),
    path("affiliate/click/", views.AffiliateClickView.as_view(), name="affiliate-click"),

    # --------------------------------------------------------------
    # Discount code validation (public)
    # --------------------------------------------------------------
    path("discount/validate/", views.ValidateDiscountView.as_view(), name="validate-discount"),

    # --------------------------------------------------------------
    # Webhook receiver (for external services to notify us)
    # --------------------------------------------------------------
    path("webhook/", views.GatingWebhookView.as_view(), name="gating-webhook"),

    # --------------------------------------------------------------
    # Admin / management endpoints (require authentication)
    # --------------------------------------------------------------
    path("my/assets/", views.MyAssetsListView.as_view(), name="my-assets"),
    path("my/assets/<uuid:pk>/", views.MyAssetDetailView.as_view(), name="my-asset-detail"),
    path("my/assets/<uuid:pk>/stats/", views.MyAssetStatsView.as_view(), name="my-asset-stats"),
    path("my/grants/", views.MyGrantsListView.as_view(), name="my-grants"),
    path("my/affiliate/", views.MyAffiliateStatsView.as_view(), name="my-affiliate-stats"),

    # --------------------------------------------------------------
    # ViewSets (if using router)
    # --------------------------------------------------------------
    path("", include(router.urls)),
    path("", include(assets_router.urls)),
]

# ----------------------------------------------------------------------
# Optional: add support for serving embed.js (client library)
# ----------------------------------------------------------------------
from django.views.generic import TemplateView
urlpatterns += [
    path("embed.js", TemplateView.as_view(template_name="gating/embed.js", content_type="application/javascript"), name="embed-js"),
]