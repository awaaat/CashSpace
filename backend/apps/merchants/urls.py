# backend/apps/merchants/urls.py
from django.urls import path
from . import views

urlpatterns = [

    # ── Public checkout (no auth) ─────────────────────────────────────────────

    # Merchant storefront
    path("pay/<slug:merchant_slug>/",
         views.MerchantLandingView.as_view(),
         name="merchant_landing"),

    # Product detail + checkout form config (includes is_test_mode flag)
    path("pay/<slug:merchant_slug>/<slug:product_slug>/",
         views.ProductCheckoutPageView.as_view(),
         name="product_checkout_page"),

    # Buyer submits identity form
    # ?mode=test → skips PayRam, returns synthetic session
    path("pay/<slug:merchant_slug>/<slug:product_slug>/checkout/",
         views.SubmitCheckoutView.as_view(),
         name="submit_checkout"),

    # Buyer polls for status
    path("pay/<slug:merchant_slug>/<slug:product_slug>/checkout/<uuid:checkout_id>/status/",
         views.CheckoutStatusView.as_view(),
         name="checkout_status"),

    # Test mode: mark checkout as completed without real payment
    path("pay/<slug:merchant_slug>/<slug:product_slug>/checkout/<uuid:checkout_id>/test-complete/",
         views.TestCompleteView.as_view(),
         name="checkout_test_complete"),

    # ── Merchant dashboard (authenticated) ───────────────────────────────────

    path("merchants/register/",
         views.MerchantRegisterView.as_view(),
         name="merchant_register"),

    path("merchants/me/",
         views.MerchantMeView.as_view(),
         name="merchant_me"),

    path("merchants/me/analytics/",
         views.MerchantAnalyticsView.as_view(),
         name="merchant_analytics"),

    # API keys — test/live keypairs, mode toggle, rotation
    path("merchants/me/keys/",
         views.MerchantAPIKeysView.as_view(),
         name="merchant_keys"),

    path("merchants/me/keys/rotate/",
         views.RotateAPIKeyView.as_view(),
         name="merchant_keys_rotate"),

    path("merchants/me/keys/toggle-mode/",
         views.ToggleModeView.as_view(),
         name="merchant_keys_toggle_mode"),

    # Sales CRM
    path("merchants/me/sales/",
         views.MerchantSalesListView.as_view(),
         name="merchant_sales"),

    path("merchants/me/sales/<uuid:pk>/",
         views.MerchantSaleDetailView.as_view(),
         name="merchant_sale_detail"),

    path("merchants/me/sales/<uuid:pk>/retrigger/",
         views.RetriggerAutomationView.as_view(),
         name="merchant_retrigger"),

    # Products CRUD
    path("merchants/me/products/",
         views.MerchantProductListView.as_view(),
         name="merchant_product_list"),

    path("merchants/me/products/<uuid:pk>/",
         views.MerchantProductDetailView.as_view(),
         name="merchant_product_detail"),

    # Test sale — simulates a complete purchase (dashboard use only)
    path("merchants/me/products/<uuid:product_id>/test-sale/",
         views.TestSaleView.as_view(),
         name="merchant_test_sale"),

    # Post-payment actions
    path("merchants/me/products/<uuid:product_id>/actions/",
         views.MerchantActionListView.as_view(),
         name="merchant_action_list"),

    path("merchants/me/products/<uuid:product_id>/actions/<uuid:pk>/",
         views.MerchantActionDetailView.as_view(),
         name="merchant_action_detail"),

    # Webhook delivery logs
    path("merchants/me/webhook-logs/",
         views.WebhookDeliveryLogListView.as_view(),
         name="merchant_webhook_logs"),

    path("merchants/me/webhook-logs/<uuid:pk>/retry/",
         views.WebhookDeliveryLogRetryView.as_view(),
         name="merchant_webhook_log_retry"),

    # ── Admin (staff only) ────────────────────────────────────────────────────

    path("merchants/admin/",
         views.AdminMerchantListView.as_view(),
         name="admin_merchant_list"),

    path("merchants/admin/<uuid:pk>/",
         views.AdminMerchantDetailView.as_view(),
         name="admin_merchant_detail"),

    path("merchants/admin/sales/",
         views.AdminAllSalesView.as_view(),
         name="admin_all_sales"),
]