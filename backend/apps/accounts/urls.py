# backend/apps/accounts/urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

urlpatterns = [
    # ── Auth ─────────────────────────────────────────────────
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify_email"),
    path("forgot-password/", views.ForgotPasswordView.as_view(), name="forgot_password"),
    path("reset-password/", views.ResetPasswordView.as_view(), name="reset_password"),

    # ── Profile ──────────────────────────────────────────────
    path("me/", views.MeView.as_view(), name="me"),
    path("change-password/", views.ChangePasswordView.as_view(), name="change_password"),

    # ── Crypto Wallets (multi‑currency) ──────────────────────
    path("wallets/", views.UserWalletListView.as_view(), name="wallet_list_create"),
    path("wallets/<uuid:pk>/", views.UserWalletDetailView.as_view(), name="wallet_detail"),
    path("wallets/<uuid:pk>/set-default/", views.SetDefaultWalletView.as_view(), name="wallet_set_default"),

    # ── Admin ────────────────────────────────────────────────
    path("admin/users/", views.AdminUserListView.as_view(), name="admin_user_list"),
    path("admin/users/<uuid:pk>/", views.AdminUserDetailView.as_view(), name="admin_user_detail"),
    path("admin/users/<uuid:pk>/suspend/", views.AdminSuspendUserView.as_view(), name="admin_suspend_user"),
    path("admin/users/<uuid:pk>/activate/", views.AdminActivateUserView.as_view(), name="admin_activate_user"),
    path("admin/audit-logs/", views.AdminAuditLogView.as_view(), name="admin_audit_logs"),
]