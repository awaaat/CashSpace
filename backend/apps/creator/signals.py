"""
apps/creator/signals.py
=======================
Django signals for the creator app.

Handles:
  - Auto‑creation of CreatorProfile when a user creates their first PayableAsset
    or logs in (optional).
  - Automatic update of asset and creator aggregated stats when a sale is completed.
  - Invalidation of caches when asset price or settings change.
  - Logging of significant events.

All operations are idempotent and wrapped in try/except to prevent signal failures
from breaking core flows.
"""

import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.core.cache import cache

from apps.accounts.models import User
from .models import CreatorProfile, PayableAsset, CreatorSale

logger = logging.getLogger("apps.creator.signals")


# ----------------------------------------------------------------------
# Auto‑create CreatorProfile on first asset creation (lazy)
# ----------------------------------------------------------------------
@receiver(post_save, sender=PayableAsset)
def ensure_creator_profile_on_asset_creation(sender, instance, created, **kwargs):
    """If a PayableAsset is created and the owner lacks a CreatorProfile, create it."""
    if not created:
        return
    try:
        profile, created = CreatorProfile.objects.get_or_create(user=instance.creator.user)
        if created:
            logger.info(f"Auto‑created CreatorProfile for user {instance.creator.user.email} upon asset creation")
    except Exception as e:
        logger.error(f"Failed to auto‑create CreatorProfile for user {instance.creator.user.email}: {e}")


# Optional: also auto‑create on user login (if you want)
# @receiver(user_logged_in)
# def ensure_creator_profile_on_login(sender, request, user, **kwargs):
#     CreatorProfile.objects.get_or_create(user=user)


# ----------------------------------------------------------------------
# Update aggregated stats when a sale is completed
# ----------------------------------------------------------------------
@receiver(post_save, sender=CreatorSale)
def update_aggregated_stats_on_sale_completion(sender, instance, created, **kwargs):
    """
    When a sale becomes COMPLETED (status change), update:
      - asset.total_sales, asset.revenue_usd
      - creator.total_sales, creator.total_revenue_usd
    Also clear relevant caches.
    """
    # Only act when status becomes COMPLETED
    if instance.status != CreatorSale.Status.COMPLETED:
        return

    # Use update_fields to prevent infinite loops if we save again
    asset = instance.asset
    creator = asset.creator

    # Update asset stats (atomic increment)
    try:
        asset.total_sales = (asset.total_sales or 0) + 1
        asset.revenue_usd = (asset.revenue_usd or 0) + instance.amount_usd
        asset.save(update_fields=["total_sales", "revenue_usd"])
        logger.debug(f"Updated asset {asset.id} stats: sales={asset.total_sales}, revenue={asset.revenue_usd}")
    except Exception as e:
        logger.error(f"Failed to update asset stats for sale {instance.id}: {e}")

    # Update creator stats (atomic increment)
    try:
        creator.total_sales = (creator.total_sales or 0) + 1
        creator.total_revenue_usd = (creator.total_revenue_usd or 0) + instance.amount_usd
        creator.save(update_fields=["total_sales", "total_revenue_usd"])
        logger.debug(f"Updated creator {creator.id} stats: sales={creator.total_sales}, revenue={creator.total_revenue_usd}")
    except Exception as e:
        logger.error(f"Failed to update creator stats for sale {instance.id}: {e}")

    # Invalidate caches for asset and creator
    cache.delete(f"creator:asset:{asset.id}:stats")
    cache.delete(f"creator:profile:{creator.id}:stats")
    cache.delete_pattern(f"creator:analytics:*")


# ----------------------------------------------------------------------
# Invalidate asset cache when asset is updated (price, title, etc.)
# ----------------------------------------------------------------------
@receiver(pre_save, sender=PayableAsset)
def invalidate_asset_cache_on_update(sender, instance, **kwargs):
    """If the asset already exists and certain fields change, clear its cache."""
    if not instance.pk:
        return  # new asset, no cache yet
    try:
        old = PayableAsset.objects.get(pk=instance.pk)
    except PayableAsset.DoesNotExist:
        return

    # Fields that affect public display or checkout
    cacheable_fields = ["price_usd", "min_price_usd", "max_price_usd", "title", "description", "is_active", "asset_type"]
    if any(getattr(old, field) != getattr(instance, field) for field in cacheable_fields):
        cache.delete(f"creator:asset:{instance.id}:public")
        cache.delete(f"creator:asset:{instance.slug}:public")
        logger.debug(f"Invalidated public cache for asset {instance.id}")


# ----------------------------------------------------------------------
# Log significant creator events (optional, using AuditLog)
# ----------------------------------------------------------------------
@receiver(post_save, sender=CreatorProfile)
def log_creator_profile_creation(sender, instance, created, **kwargs):
    if created:
        from apps.accounts.models import AuditLog
        AuditLog.objects.create(
            user=instance.user,
            action="creator_profile_created",
            metadata={"profile_id": str(instance.id)},
        )
        logger.info(f"Creator profile created for user {instance.user.email}")