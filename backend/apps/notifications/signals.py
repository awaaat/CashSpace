from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from apps.payments.models import Payment, UserCryptoWallet
from .models import Notification


@receiver(post_save, sender=Payment)
def handle_payment_notification(sender, instance, created, **kwargs):
    if created:
        Notification.create_notification(
            user=instance.user,
            notification_type=Notification.Type.PAYMENT_SUCCESS,
            title="Payment Initiated",
            message=f"Your payment of ${instance.amount_usd} has been initiated.",
            level=Notification.Level.INFO,
            related_object=instance,
        )
    elif instance.status == "FILLED":
        Notification.create_notification(
            user=instance.user,
            notification_type=Notification.Type.PAYOUT_COMPLETED,
            title="Payout Completed",
            message=f"Your payout of ${instance.payout_usd_equivalent} has been sent to your wallet.",
            level=Notification.Level.SUCCESS,
            related_object=instance,
        )


@receiver(post_save, sender=UserCryptoWallet)
def handle_wallet_notification(sender, instance, created, **kwargs):
    # update_fields is a frozenset or None — NOT a dict. Never call .get() on it.
    update_fields = kwargs.get("update_fields")  # frozenset | None

    if created:
        Notification.create_notification(
            user=instance.user,
            notification_type=Notification.Type.WALLET_ADDED,
            title="New Wallet Added",
            message=f"{instance.currency_code} wallet on {instance.blockchain_code} was added.",
            level=Notification.Level.INFO,
            related_object=instance,
        )
    elif instance.is_default:
        # Only fire the "default changed" notification when is_default was actually
        # part of this save (i.e. update_fields includes it, or full save with no update_fields).
        if update_fields is None or "is_default" in update_fields:
            Notification.create_notification(
                user=instance.user,
                notification_type=Notification.Type.WALLET_UPDATED,
                title="Default Wallet Updated",
                message=f"{instance.currency_code} on {instance.blockchain_code} is now your default wallet.",
                level=Notification.Level.INFO,
                related_object=instance,
            )


@receiver(post_delete, sender=UserCryptoWallet)
def handle_wallet_deleted(sender, instance, **kwargs):
    Notification.create_notification(
        user=instance.user,
        notification_type=Notification.Type.WALLET_DELETED,
        title="Wallet Removed",
        message=f"{instance.currency_code} wallet on {instance.blockchain_code} was deleted.",
        level=Notification.Level.WARNING,
        related_object=instance,
    )