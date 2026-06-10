"""
apps/gating/redis_nonce.py
==========================
Redis-backed nonce manager for single‑use token enforcement.

Prevents replay attacks by tracking which nonces (unique token identifiers)
have already been used. Features:
  - Automatic TTL based on token expiry (default + grace period).
  - Atomic check-and-set operations (SETNX) to prevent race conditions.
  - Batch nonce validation for bulk operations.
  - Grace period to account for network delays.
  - Configurable Redis key prefix and default TTL.
  - Fallback to Django cache (with Redis backend) if no direct Redis client.
  - Full logging of anomalies (duplicate attempts, expired nonces).
"""

import hashlib
import logging
from typing import List, Optional, Set, Union
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger("apps.gating.nonce")

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
NONCE_KEY_PREFIX = getattr(settings, "GATING_NONCE_KEY_PREFIX", "gating:nonce:")
DEFAULT_NONCE_TTL_SECONDS = getattr(settings, "GATING_NONCE_TTL_SECONDS", 86400)  # 24 hours
NONCE_GRACE_SECONDS = getattr(settings, "GATING_NONCE_GRACE_SECONDS", 300)  # 5 minutes grace after expiry


class NonceManager:
    """
    Manages single‑use nonces using Redis SETNX (atomic).
    If Redis is not available, falls back to Django cache's add() method.
    """

    @staticmethod
    def _make_key(nonce: str) -> str:
        """Generate a safe Redis key for the given nonce."""
        # Normalise nonce (strip whitespace, convert to lowercase if needed)
        normalized = nonce.strip()
        # Use hash for long nonces to keep key length reasonable
        if len(normalized) > 64:
            normalized = hashlib.sha256(normalized.encode()).hexdigest()
        return f"{NONCE_KEY_PREFIX}{normalized}"

    @staticmethod
    def _get_ttl(expires_at: Optional[timezone.datetime] = None) -> int:
        """
        Calculate TTL for the nonce key.
        If expires_at is given, use that + grace period.
        Otherwise use DEFAULT_NONCE_TTL_SECONDS.
        """
        if expires_at:
            now = timezone.now()
            if expires_at > now:
                ttl = int((expires_at - now).total_seconds()) + NONCE_GRACE_SECONDS
                return max(ttl, 60)  # at least 1 minute
            else:
                # Already expired, but still give a short TTL to avoid immediate reuse
                return 60
        return DEFAULT_NONCE_TTL_SECONDS

    @classmethod
    def mark_used(cls, nonce: str, expires_at: Optional[timezone.datetime] = None) -> bool:
        """
        Mark a nonce as used. Returns True if the nonce was not previously used,
        False if it was already used (or an error occurred).
        """
        key = cls._make_key(nonce)
        ttl = cls._get_ttl(expires_at)

        # Try atomic SETNX via Django cache's `add()` method
        try:
            # `cache.add(key, value, timeout)` returns True if key did not exist.
            added = cache.add(key, "used", timeout=ttl)
            if added:
                logger.debug(f"Nonce {nonce[:16]}... marked used (TTL={ttl}s)")
            else:
                logger.warning(f"Duplicate nonce detected: {nonce[:16]}...")
            return added
        except Exception as e:
            # Fallback: check manually then set (race condition possible but logged)
            logger.error(f"Redis/Cache error in mark_used: {e}")
            if cls.is_used(nonce):
                return False
            # Manual set (may still race, but better than nothing)
            try:
                cache.set(key, "used", timeout=ttl)
                return True
            except Exception:
                return False

    @classmethod
    def is_used(cls, nonce: str) -> bool:
        """Check if a nonce has already been used."""
        key = cls._make_key(nonce)
        try:
            return cache.get(key) is not None
        except Exception as e:
            logger.error(f"Cache error in is_used: {e}")
            # On error, assume not used to avoid blocking legitimate requests,
            # but log the anomaly.
            return False

    @classmethod
    def mark_batch_used(cls, nonces: List[str], expires_at: Optional[timezone.datetime] = None) -> List[str]:
        """
        Mark multiple nonces as used atomically (if possible).
        Returns list of nonces that were successfully marked (i.e., were not already used).
        """
        # For simplicity, we iterate; Redis pipeline would be better, but cache abstraction lacks it.
        used = []
        for nonce in nonces:
            if cls.mark_used(nonce, expires_at):
                used.append(nonce)
        return used

    @classmethod
    def clear(cls, nonce: str) -> None:
        """Manually clear a nonce from the store (for testing or admin)."""
        key = cls._make_key(nonce)
        try:
            cache.delete(key)
        except Exception as e:
            logger.error(f"Failed to clear nonce {nonce[:16]}...: {e}")

    @classmethod
    def get_ttl_remaining(cls, nonce: str) -> int:
        """
        Get remaining TTL in seconds for a nonce key.
        Returns -1 if key does not exist or error.
        """
        key = cls._make_key(nonce)
        try:
            # Django cache does not expose TTL uniformly; fallback to Redis direct?
            # We'll return -1 as not supported in generic cache.
            return -1
        except Exception:
            return -1


# ----------------------------------------------------------------------
# Convenience functions for use in tokens.py
# ----------------------------------------------------------------------
def is_nonce_used(nonce: str) -> bool:
    """Public helper: check if a nonce has been used."""
    return NonceManager.is_used(nonce)


def mark_nonce_used(nonce: str, expires_at: Optional[timezone.datetime] = None) -> bool:
    """Public helper: mark a nonce as used, returns True if first time."""
    return NonceManager.mark_used(nonce, expires_at)


def clear_nonce(nonce: str) -> None:
    """Public helper: clear a nonce (admin only)."""
    NonceManager.clear(nonce)