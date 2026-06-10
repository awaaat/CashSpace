import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone

User = get_user_model()
logger = logging.getLogger("apps.accounts")


def _create_verification_token(user):
    from .models import EmailVerificationToken
    return EmailVerificationToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(hours=24),
    )


def _create_reset_token(user):
    from .models import PasswordResetToken
    return PasswordResetToken.objects.create(
        user=user,
        expires_at=timezone.now() + timedelta(hours=1),
    )


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_verification_email(self, user_id: str):
    """Send email verification link to newly registered user."""
    try:
        user = User.objects.get(id=user_id)
        token_obj = _create_verification_token(user)
        verify_url = f"{settings.FRONTEND_URL}/verify-email?token={token_obj.token}"

        send_mail(
            subject="Verify your CashSpace email",
            message=(
                f"Hi {user.first_name or user.email},\n\n"
                f"Please verify your email address by clicking the link below:\n\n"
                f"{verify_url}\n\n"
                f"This link expires in 24 hours.\n\n"
                f"If you didn't create a CashSpace account, you can ignore this email.\n\n"
                f"— The CashSpace Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Verification email sent to %s", user.email)
    except User.DoesNotExist:
        logger.error("send_verification_email: user %s not found", user_id)
    except Exception as exc:
        logger.error("Failed to send verification email to user %s: %s", user_id, exc)
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_password_reset_email(self, user_id: str):
    """Send password reset link."""
    try:
        user = User.objects.get(id=user_id)
        token_obj = _create_reset_token(user)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token_obj.token}"

        send_mail(
            subject="Reset your CashSpace password",
            message=(
                f"Hi {user.first_name or user.email},\n\n"
                f"We received a request to reset your password. Click the link below:\n\n"
                f"{reset_url}\n\n"
                f"This link expires in 1 hour. If you didn't request a password reset, "
                f"please ignore this email.\n\n"
                f"— The CashSpace Team"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info("Password reset email sent to %s", user.email)
    except User.DoesNotExist:
        logger.error("send_password_reset_email: user %s not found", user_id)
    except Exception as exc:
        logger.error("Failed to send password reset email to user %s: %s", user_id, exc)
        raise self.retry(exc=exc)