# apps/accounts/views.py
# Enterprise-grade views supporting multi-chain crypto wallets

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.core.permissions import IsActiveUser, IsOwnerOrAdmin
from apps.payments.models import UserCryptoWallet
from apps.payments.serializers import (
    CryptoWalletSerializer,
    CryptoWalletCreateSerializer,
    CryptoWalletUpdateSerializer,
)

from .models import AuditLog, EmailVerificationToken, PasswordResetToken
from .serializers import (
    AdminUserDetailSerializer,
    AdminUserListSerializer,
    AuditLogSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UpdateProfileSerializer,
    UserProfileSerializer,
)
from .tasks import send_verification_email, send_password_reset_email

User = get_user_model()
logger = logging.getLogger("apps.accounts")


def get_client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    return xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR", "")


class AuthRateThrottle(AnonRateThrottle):
    rate = "5/minute"
    scope = "auth"


# ── Auth ──────────────────────────────────────────────────────────────────────

class RegisterView(generics.CreateAPIView):
    """POST /api/v1/auth/register/"""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Kick off verification email async via Celery
        send_verification_email.delay(str(user.id))

        # Log registration
        AuditLog.objects.create(
            user=user,
            action=AuditLog.Action.REGISTER,
            ip_address=get_client_ip(request),
            user_agent=request.META.get("HTTP_USER_AGENT", ""),
        )

        return Response(
            {
                "detail": "Account created. Please check your email to verify your account.",
                "user_id": str(user.id),
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """POST /api/v1/auth/login/ — returns access + refresh tokens."""

    throttle_classes = [AuthRateThrottle]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            email = request.data.get("email", "").lower()
            try:
                user = User.objects.get(email=email)
                user.reset_failed_login()
                user.last_login_ip = get_client_ip(request)
                user.save(update_fields=["last_login_ip"])
                AuditLog.objects.create(
                    user=user,
                    action=AuditLog.Action.LOGIN,
                    ip_address=get_client_ip(request),
                    user_agent=request.META.get("HTTP_USER_AGENT", ""),
                )
            except User.DoesNotExist:
                pass
        else:
            # Increment failed attempts on bad credentials
            email = request.data.get("email", "").lower()
            try:
                user = User.objects.get(email=email)
                user.increment_failed_login()
                if user.is_locked:
                    AuditLog.objects.create(
                        user=user,
                        action=AuditLog.Action.ACCOUNT_LOCKED,
                        ip_address=get_client_ip(request),
                    )
            except User.DoesNotExist:
                pass

        return response


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — blacklist the refresh token."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            token = RefreshToken(refresh_token)
            token.blacklist()
            AuditLog.objects.create(
                user=request.user,
                action=AuditLog.Action.LOGOUT,
                ip_address=get_client_ip(request),
            )
            return Response({"detail": "Logged out successfully."})
        except Exception:
            return Response({"detail": "Invalid or already blacklisted token."}, status=400)


class VerifyEmailView(APIView):
    """GET /api/v1/auth/verify-email/?token=<uuid>"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        token_value = request.query_params.get("token")
        if not token_value:
            return Response({"detail": "Token is required."}, status=400)

        try:
            token_obj = EmailVerificationToken.objects.select_related("user").get(token=token_value)
        except EmailVerificationToken.DoesNotExist:
            return Response({"detail": "Invalid verification link."}, status=400)

        if not token_obj.is_valid:
            return Response({"detail": "This verification link has expired or already been used."}, status=400)

        user = token_obj.user
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

        token_obj.used_at = timezone.now()
        token_obj.save(update_fields=["used_at"])

        AuditLog.objects.create(user=user, action=AuditLog.Action.EMAIL_VERIFIED)
        return Response({"detail": "Email verified successfully. You can now log in."})


class ForgotPasswordView(APIView):
    """POST /api/v1/auth/forgot-password/"""

    permission_classes = [permissions.AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        # Always return 200 to prevent user enumeration
        try:
            user = User.objects.get(email=email, is_active=True)
            send_password_reset_email.delay(str(user.id))
        except User.DoesNotExist:
            pass

        return Response({"detail": "If an account with that email exists, a reset link has been sent."})


class ResetPasswordView(APIView):
    """POST /api/v1/auth/reset-password/"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            token_obj = PasswordResetToken.objects.select_related("user").get(
                token=serializer.validated_data["token"]
            )
        except PasswordResetToken.DoesNotExist:
            return Response({"detail": "Invalid or expired reset link."}, status=400)

        if not token_obj.is_valid:
            return Response({"detail": "This reset link has expired or already been used."}, status=400)

        user = token_obj.user
        user.set_password(serializer.validated_data["new_password"])
        user.save()

        token_obj.used_at = timezone.now()
        token_obj.save(update_fields=["used_at"])

        AuditLog.objects.create(user=user, action=AuditLog.Action.PASSWORD_CHANGE)
        return Response({"detail": "Password reset successfully. Please log in."})


# ── Profile ───────────────────────────────────────────────────────────────────

class MeView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/me/ — current user's profile (includes crypto wallets)."""

    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def get_serializer_class(self):
        if self.request.method in ("PUT", "PATCH"):
            return UpdateProfileSerializer
        return UserProfileSerializer

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        response = super().update(request, *args, **kwargs)
        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.Action.PROFILE_UPDATED,
            ip_address=get_client_ip(request),
        )
        return response


# ── Crypto Wallet Management (replaces old WalletView) ────────────────────────

class UserWalletListView(generics.ListCreateAPIView):
    """
    GET /api/v1/auth/wallets/ — list all crypto wallets for authenticated user.
    POST /api/v1/auth/wallets/ — add a new crypto wallet.
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return CryptoWalletCreateSerializer
        return CryptoWalletSerializer

    def get_queryset(self):
        return UserCryptoWallet.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        wallet = serializer.save(user=self.request.user)
        AuditLog.objects.create(
            user=self.request.user,
            action=AuditLog.Action.WALLET_ADDED,
            ip_address=get_client_ip(self.request),
            metadata={
                "blockchain": wallet.blockchain_code,
                "currency": wallet.currency_code,
                "address": wallet.wallet_address,
                "is_default": wallet.is_default,
            }
        )


class UserWalletDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET /api/v1/auth/wallets/<id>/ — retrieve wallet details.
    PATCH /api/v1/auth/wallets/<id>/ — update label, active status, default flag.
    DELETE /api/v1/auth/wallets/<id>/ — delete a wallet (soft delete via is_active=False? Actually hard delete allowed).
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser, IsOwnerOrAdmin]
    serializer_class = CryptoWalletUpdateSerializer

    def get_queryset(self):
        return UserCryptoWallet.objects.filter(user=self.request.user)

    def perform_update(self, serializer):
        old_is_default = self.get_object().is_default
        wallet = serializer.save()
        if wallet.is_default and not old_is_default:
            AuditLog.objects.create(
                user=self.request.user,
                action=AuditLog.Action.WALLET_SET_DEFAULT,
                ip_address=get_client_ip(self.request),
                metadata={
                    "blockchain": wallet.blockchain_code,
                    "currency": wallet.currency_code,
                    "address": wallet.wallet_address,
                }
            )
        else:
            AuditLog.objects.create(
                user=self.request.user,
                action=AuditLog.Action.WALLET_UPDATED,
                ip_address=get_client_ip(self.request),
                metadata={
                    "blockchain": wallet.blockchain_code,
                    "currency": wallet.currency_code,
                    "updated_fields": list(serializer.validated_data.keys()),
                }
            )

    def perform_destroy(self, instance):
        # Log before deletion
        AuditLog.objects.create(
            user=self.request.user,
            action=AuditLog.Action.WALLET_DELETED,
            ip_address=get_client_ip(self.request),
            metadata={
                "blockchain": instance.blockchain_code,
                "currency": instance.currency_code,
                "address": instance.wallet_address,
            }
        )
        instance.delete()


class SetDefaultWalletView(APIView):
    """
    POST /api/v1/auth/wallets/<id>/set-default/
    Convenience endpoint to set a wallet as default for its (blockchain, currency).
    """

    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def post(self, request, pk):
        try:
            wallet = UserCryptoWallet.objects.get(pk=pk, user=request.user)
        except UserCryptoWallet.DoesNotExist:
            return Response({"detail": "Wallet not found."}, status=404)

        # Unset any other default for same (user, blockchain, currency)
        UserCryptoWallet.objects.filter(
            user=request.user,
            blockchain_code=wallet.blockchain_code,
            currency_code=wallet.currency_code,
            is_default=True
        ).exclude(id=wallet.id).update(is_default=False)

        wallet.is_default = True
        wallet.save(update_fields=["is_default"])

        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.Action.WALLET_SET_DEFAULT,
            ip_address=get_client_ip(request),
            metadata={
                "blockchain": wallet.blockchain_code,
                "currency": wallet.currency_code,
                "address": wallet.wallet_address,
            }
        )
        return Response({"detail": "Default wallet updated successfully."})


# ── Change Password (kept separate) ──────────────────────────────────────────

class ChangePasswordView(APIView):
    """POST /api/v1/auth/change-password/"""

    permission_classes = [permissions.IsAuthenticated, IsActiveUser]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()
        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.Action.PASSWORD_CHANGE,
            ip_address=get_client_ip(request),
        )
        return Response({"detail": "Password changed successfully. Please log in again."})


# ── Admin Views (updated for multi-wallet) ────────────────────────────────────

class AdminUserListView(generics.ListAPIView):
    """GET /api/v1/auth/admin/users/ — list all users (staff only)."""

    serializer_class = AdminUserListSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filterset_fields = ["role", "is_active", "is_email_verified", "is_kyc_verified"]
    search_fields = ["email", "first_name", "last_name"]
    ordering_fields = ["date_joined", "last_login", "email"]

    def get_queryset(self):
        return User.objects.prefetch_related("payments", "crypto_wallets").order_by("-date_joined")


class AdminUserDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/v1/auth/admin/users/<id>/ — manage a single user."""

    serializer_class = AdminUserDetailSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    queryset = User.objects.all().prefetch_related("crypto_wallets")


class AdminSuspendUserView(APIView):
    """POST /api/v1/auth/admin/users/<id>/suspend/"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=404)

        if user == request.user:
            return Response({"detail": "You cannot suspend yourself."}, status=400)

        user.is_active = False
        user.save(update_fields=["is_active"])

        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.Action.ADMIN_ACTION,
            ip_address=get_client_ip(request),
            metadata={"action": "suspend_user", "target_user_id": str(user.id), "target_email": user.email},
        )
        return Response({"detail": f"User {user.email} has been suspended."})


class AdminActivateUserView(APIView):
    """POST /api/v1/auth/admin/users/<id>/activate/"""

    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, pk):
        try:
            user = User.objects.get(pk=pk)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=404)

        user.is_active = True
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["is_active", "failed_login_attempts", "locked_until"])

        AuditLog.objects.create(
            user=request.user,
            action=AuditLog.Action.ADMIN_ACTION,
            ip_address=get_client_ip(request),
            metadata={"action": "activate_user", "target_user_id": str(user.id)},
        )
        return Response({"detail": f"User {user.email} has been activated."})


class AdminAuditLogView(generics.ListAPIView):
    """GET /api/v1/auth/admin/audit-logs/"""

    serializer_class = AuditLogSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
    filterset_fields = ["action"]
    search_fields = ["user__email", "ip_address"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return AuditLog.objects.select_related("user").order_by("-created_at")