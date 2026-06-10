from django.urls import path

from . import views

urlpatterns = [
    # User endpoints
    path("initiate/", views.InitiatePaymentView.as_view(), name="payment_initiate"),
    path("", views.PaymentListView.as_view(), name="payment_list"),
    path("<uuid:pk>/", views.PaymentDetailView.as_view(), name="payment_detail"),
    path("<uuid:pk>/status/", views.CheckPaymentStatusView.as_view(), name="payment_status"),

    # Webhook
    path("webhook/", views.PayRamWebhookView.as_view(), name="payment_webhook"),

    # Admin
    path("admin/", views.AdminPaymentListView.as_view(), name="admin_payment_list"),
]