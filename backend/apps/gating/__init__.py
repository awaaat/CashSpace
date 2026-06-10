"""
Gating app for CashSpace – URL-as-payable-asset and gated access.

This app provides:
  - Pay‑to‑unlock for any external URL, file, API key, Telegram group, Discord role.
  - Signed access tokens (UUID, HMAC, JWT, PASETO).
  - Proxy streaming of paid content.
  - Affiliate tracking and discount codes.
  - Subscription and tiered pricing.
  - Drip content (multi‑step unlocks).
  - Dynamic pricing based on demand.
"""

default_app_config = "apps.gating.apps.GatingConfig"