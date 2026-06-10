"""
apps/creator/urls.py
====================
URL configuration for the creator app.

Endpoints:
  Public:
    - /creator/pay/<slug>/                 → asset details (checkout page)
    - /creator/pay/<slug>/checkout/        → submit payment

  Authenticated (Creator):
    - /creator/profile/                     → get/update own profile
    - /creator/assets/                      → list/create assets
    - /creator/assets/<uuid>/               → retrieve/update/delete asset
    - /creator/assets/<uuid>/stats/         → asset analytics
    - /creator/assets/<uuid>/affiliate/     → affiliate program
    - /creator/assets/<uuid>/discounts/     → list/create discount codes
    - /creator/assets/<uuid>/discounts/<id>/ → update/delete discount code
    - /creator/sales/                       → list sales
    - /creator/sales/<uuid>/                → sale detail
    - /creator/stats/                       → global creator stats

  Webhook (no auth):
    - /creator/webhook/                     → payment confirmation from PayRam
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# No router needed – all views are APIViews or generics

urlpatterns = [
    # ── Public (no authentication) ──────────────────────────────────────────
    path("creator/pay/<slug:slug>/", views.PublicAssetPageView.as_view(), name="creator_public_asset"),
    path("creator/pay/<slug:slug>/checkout/", views.PublicCheckoutView.as_view(), name="creator_public_checkout"),

    # ── Creator Profile ─────────────────────────────────────────────────────
    path("creator/profile/", views.CreatorProfileView.as_view(), name="creator_profile"),

    # ── Asset Management ────────────────────────────────────────────────────
    path("creator/assets/", views.CreatorAssetListView.as_view(), name="creator_asset_list"),
    path("creator/assets/<uuid:pk>/", views.CreatorAssetDetailView.as_view(), name="creator_asset_detail"),
    path("creator/assets/<uuid:pk>/stats/", views.CreatorAssetStatsView.as_view(), name="creator_asset_stats"),

    # ── Affiliate Program ───────────────────────────────────────────────────
    path("creator/assets/<uuid:asset_id>/affiliate/", views.CreatorAffiliateProgramView.as_view(), name="creator_affiliate"),

    # ── Discount Codes ──────────────────────────────────────────────────────
    path("creator/assets/<uuid:asset_id>/discounts/", views.CreatorDiscountCodeListView.as_view(), name="creator_discount_list"),
    path("creator/assets/<uuid:asset_id>/discounts/<uuid:pk>/", views.CreatorDiscountCodeDetailView.as_view(), name="creator_discount_detail"),

    # ── Sales ───────────────────────────────────────────────────────────────
    path("creator/sales/", views.CreatorSalesListView.as_view(), name="creator_sales_list"),
    path("creator/sales/<uuid:pk>/", views.CreatorSaleDetailView.as_view(), name="creator_sale_detail"),

    # ── Global Stats ────────────────────────────────────────────────────────
    path("creator/stats/", views.CreatorStatsView.as_view(), name="creator_stats"),

    # ── Webhook (payment confirmation) ──────────────────────────────────────
    path("creator/webhook/", views.CreatorWebhookView.as_view(), name="creator_webhook"),
]