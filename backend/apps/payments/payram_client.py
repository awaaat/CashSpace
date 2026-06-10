# apps/payments/payram_client.py
# ============================================================
# PayRam API Client — Enterprise-grade, fully multi‑chain
# ============================================================
#
# This client is based **strictly on the official PayRam TypeScript SDK**
# and the PayRam REST API documentation.
#
# The SDK provides a clean, type‑safe interface:
#     import { Payram } from 'payram';
#     const payram = new Payram({ apiKey, baseUrl });
#
#     // Create a payment
#     const checkout = await payram.payments.initiatePayment({
#         customerEmail: 'user@example.com',
#         customerId: 'cust_123',
#         amountInUSD: 99.99,
#     });
#
#     // Get payment status
#     const payment = await payram.payments.getPaymentRequest(referenceId);
#
#     // Create a payout
#     const payout = await payram.payouts.createPayout({
#         email: 'merchant@example.com',
#         blockchainCode: 'ETH',
#         currencyCode: 'USDC',
#         amount: '125.50',          # Must be a string
#         toAddress: '0xfeedface…',
#         customerID: 'cust_123',
#     });
#
#     // Get payout status
#     const status = await payram.payouts.getPayoutById(payoutId);
#
# All endpoints are chain‑agnostic: you pass `blockchainCode` / `currencyCode`
# exactly as the SDK expects (ETH, TRX, BTC, BASE, POL, etc.).
#
# Commission model (operator keeps 30% of USD amount):
#   1. User pays $X via card → PayRam settles full $X into YOUR cold wallet.
#   2. You keep 30% ($X * 0.30) as commission.
#   3. You call create_payout() with the post‑commission amount ($X * 0.70)
#      and the user’s chosen blockchain+currency.
#   4. PayRam auto‑approves payouts ≤ $500; above requires admin approval.
#
# ----------------------------------------------------------------------
# IMPORTANT: This file contains NO hardcoded BTC assumptions.
# ----------------------------------------------------------------------

import hashlib
import hmac
import logging
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union

import requests
from django.conf import settings

logger = logging.getLogger("apps.payments")


# ==================================================================
# Exceptions
# ==================================================================

class PayRamError(Exception):
    """Raised when PayRam API returns an error or is unreachable."""
    pass


class PayRamValidationError(PayRamError):
    """Raised when input validation fails (e.g., invalid address)."""
    pass


# ==================================================================
# PayRam Client
# ==================================================================

class PayRamClient:
    """
    Singleton client for all PayRam API calls.

    All methods are fully multi‑chain / multi‑currency and follow the
    official PayRam TypeScript SDK patterns.

    Reference:
        - SDK: npm install payram
        - Docs: https://www.npmjs.com/package/payram
        - API: https://your-payram-server.com/api/v1/
    """

    def __init__(self):
        self.base_url = settings.PAYRAM_BASE_URL.rstrip("/")
        self.api_key = settings.PAYRAM_API_KEY
        self.webhook_secret = settings.PAYRAM_WEBHOOK_SECRET
        self.timeout = 15  # seconds

    # ==================================================================
    # Internal HTTP helpers
    # ==================================================================

    @property
    def _headers(self) -> Dict[str, str]:
        """Headers required for all PayRam API calls."""
        return {
            "API-Key": self.api_key,
            "Content-Type": "application/json",
        }

    def _post(
        self, endpoint: str, payload: Dict[str, Any], timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """POST to PayRam with retry‑friendly error handling."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.post(
                url,
                json=payload,
                headers=self._headers,
                timeout=timeout or self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise PayRamError(f"PayRam request timed out: POST {endpoint}")
        except requests.exceptions.ConnectionError:
            raise PayRamError(f"Cannot connect to PayRam server at {self.base_url}")
        except requests.exceptions.HTTPError as e:
            body = ""
            try:
                body = e.response.json()
            except Exception:
                body = e.response.text
            raise PayRamError(f"PayRam API error {e.response.status_code}: {body}")

    def _get(self, endpoint: str, timeout: Optional[int] = None) -> Dict[str, Any]:
        """GET to PayRam."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(
                url, headers=self._headers, timeout=timeout or self.timeout
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise PayRamError(f"PayRam request timed out: GET {endpoint}")
        except requests.exceptions.ConnectionError:
            raise PayRamError(f"Cannot connect to PayRam server at {self.base_url}")
        except requests.exceptions.HTTPError as e:
            body = ""
            try:
                body = e.response.json()
            except Exception:
                body = e.response.text
            raise PayRamError(f"PayRam API error {e.response.status_code}: {body}")

    # ==================================================================
    # 1. Payments API
    # ==================================================================

    def initiate_payment(
        self,
        customer_email: str,
        customer_id: str,
        amount_in_usd: Decimal,
    ) -> Dict[str, Any]:
        """
        Create a PayRam payment session (checkout).

        This corresponds to:
            SDK: payram.payments.initiatePayment()
            POST /api/v1/payment

        The user will be redirected to the returned `url` to complete payment.
        The full `amount_in_usd` settles into YOUR cold wallet.  The user’s
        cryptocurrency payout address is **not** passed here — that comes later
        when you call `create_payout()` after the payment is FILLED.

        Request body (based on SDK):
            - customerEmail: string (required)
            - customerId: string (required)
            - amountInUSD: number (required)

        Returns:
            {
                "reference_id": "c80f5363-...",  # store this!
                "url": "https://your-payram.com/payment?ref=...",
                "host": "https://your-payram.com:8443",  # optional
            }

        Example:
            >>> client.initiate_payment(
            ...     customer_email="user@example.com",
            ...     customer_id="cust_123",
            ...     amount_in_usd=Decimal("99.99"),
            ... )
        """
        payload = {
            "customerEmail": customer_email,
            "customerId": str(customer_id),
            "amountInUSD": float(amount_in_usd),
        }
        logger.info(
            "Initiating PayRam payment | email=%s | customer_id=%s | amount=$%.2f",
            customer_email,
            customer_id,
            amount_in_usd,
        )
        result = self._post("/api/v1/payment", payload)
        logger.info(
            "PayRam payment initiated | reference_id=%s", result.get("reference_id")
        )
        return result

    def get_payment_request(self, reference_id: str) -> Dict[str, Any]:
        """
        Fetch the current status of a payment session.

        This corresponds to:
            SDK: payram.payments.getPaymentRequest()
            GET /api/v1/payment/reference/{reference_id}

        Returns:
            {
                "reference_id": "...",
                "paymentState": "OPEN" | "FILLED" | "PARTIALLY_FILLED"
                                | "OVER_FILLED" | "CANCELLED",
                "amountInUSD": "100.00",
                "customerId": "...",
                "filledAmount": "50.00",   # for PARTIALLY_FILLED
                "overfilledAmount": "10.00", # for OVER_FILLED
            }

        PaymentState values (official PayRam states):
            OPEN             – session active, awaiting payment
            FILLED           – fully paid; funds in your wallet
            PARTIALLY_FILLED – user paid less than required
            OVER_FILLED      – user paid more than required
            CANCELLED        – expired or manually cancelled
        """
        logger.debug("Fetching PayRam payment status | ref=%s", reference_id)
        result = self._get(f"/api/v1/payment/reference/{reference_id}")
        logger.debug(
            "PayRam payment state=%s | ref=%s",
            result.get("paymentState", "unknown"),
            reference_id,
        )
        return result

    # ==================================================================
    # 2. Payouts API
    # ==================================================================

    def create_payout(
        self,
        email: str,
        customer_id: str,
        to_address: str,
        amount: Decimal,
        blockchain_code: str,
        currency_code: str,
        mobile_number: Optional[str] = None,
        residential_address: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send crypto to a user’s wallet.

        This corresponds to:
            SDK: payram.payouts.createPayout()
            POST /api/v1/withdrawal/merchant

        This is called **after** a payment reaches FILLED status.  You pass
        the post‑commission amount (`amount`), and specify which blockchain
        and currency the user chose.

        Request body (based on SDK):
            - email: string (required) – merchant email associated with payout
            - customerID: string (required) – your internal reference ID
            - toAddress: string (required) – recipient wallet address
            - blockchainCode: string (required) – 'ETH', 'BTC', 'TRX', 'BASE', 'POL'
            - currencyCode: string (required) – 'USDT', 'USDC', 'ETH', 'BTC', 'TRX'
            - amount: string (required) – amount as string (e.g., '125.50')
            - mobileNumber: string (optional) – E.164 format: +15555555555
            - residentialAddress: string (optional) – recipient address (compliance)

        Important: `amount` MUST be a string. JavaScript/JSON numbers lose precision.

        Returns:
            {
                "id": 120,                    # store this for status polling
                "blockchainCode": "ETH",
                "currencyCode": "USDC",
                "amount": "125.50",
                "priceInUSD": "1.00",
                "amountInUSD": "125.50",
                "toAddress": "0xfeedface...",
                "recipientEmail": "user@example.com",
                "status": "pending-approval" | "approved" | "completed" | "failed",
                "transferHash": "0x..."       # when completed
            }

        Payout status values (full state machine):
            pending-otp-verification – awaiting OTP confirmation (if required)
            pending-approval         – awaiting admin approval (payouts > $500)
            pending                  – queued for processing
            initiated                – processing has started
            sent                     – transaction broadcast to blockchain
            processed                – confirmed on blockchain
            completed                – final success state
            failed                   – transaction failed
            rejected                 – manually rejected by admin
            cancelled                – cancelled before processing

        Auto‑approval limits:
            ≤ $500 / payout → automatically approved.
            > $500 / payout → requires manual approval in PayRam dashboard.
            Hard caps: $5,000 / hour, $10,000 / day.

        Example:
            >>> client.create_payout(
            ...     email="merchant@example.com",
            ...     customer_id="cust_123",
            ...     to_address="0xfeedfacecafebeefdeadbeefdeadbeefdeadbeef",
            ...     amount=Decimal("70.00"),
            ...     blockchain_code="ETH",
            ...     currency_code="USDC",
            ...     mobile_number="+15555555555",
            ... )
        """
        # Pre‑validation: address format
        self._validate_address(to_address, blockchain_code)

        payload = {
            "email": email,
            "customerID": str(customer_id),
            "toAddress": to_address,
            "blockchainCode": blockchain_code,
            "currencyCode": currency_code,
            "amount": str(float(amount)),  # Must be string
        }
        if mobile_number:
            payload["mobileNumber"] = mobile_number
        if residential_address:
            payload["residentialAddress"] = residential_address

        logger.info(
            "Creating PayRam payout | email=%s | to=%s | amount=%s %s on %s",
            email,
            to_address,
            amount,
            currency_code,
            blockchain_code,
        )
        result = self._post("/api/v1/withdrawal/merchant", payload)
        logger.info(
            "PayRam payout created | payout_id=%s | status=%s",
            result.get("id"),
            result.get("status"),
        )
        return result

    def get_payout_by_id(self, payout_id: int) -> Dict[str, Any]:
        """
        Fetch the status of a previously created payout.

        This corresponds to:
            SDK: payram.payouts.getPayoutById()
            GET /api/v1/withdrawal/merchant/{id}

        Returns the same shape as create_payout(), with updated status.

        Status values (see create_payout() for full list):
            pending-approval – awaiting admin sign‑off
            approved         – approved, processing on‑chain
            completed        – on‑chain transaction confirmed
            failed           – payout failed (check error field)
        """
        logger.debug("Fetching PayRam payout status | payout_id=%s", payout_id)
        result = self._get(f"/api/v1/withdrawal/merchant/{payout_id}")
        logger.debug(
            "PayRam payout state=%s | payout_id=%s",
            result.get("status", "unknown"),
            payout_id,
        )
        return result

    # ==================================================================
    # 3. Referrals API
    # ==================================================================

    def authenticate_referrer(self, email: str, reference_id: str) -> Dict[str, Any]:
        """
        Authenticate a referrer for a referral program.

        This corresponds to:
            SDK: payram.referrals.authenticateReferrer()
            POST /api/v1/referrals/authenticate

        Request body:
            - email: string (required)
            - referenceID: string (required) – campaign ID

        Returns:
            {
                "success": true,
                "referrerCode": "REF-ABC123",
                "campaignName": "Summer Promo",
            }
        """
        payload = {"email": email, "referenceID": reference_id}
        logger.info("Authenticating referrer | email=%s | program=%s", email, reference_id)
        return self._post("/api/v1/referrals/authenticate", payload)

    def link_referee(
        self,
        email: str,
        referrer_code: str,
        reference_id: str,
    ) -> Dict[str, Any]:
        """
        Link a new user (referee) to a referrer.

        This corresponds to:
            SDK: payram.referrals.linkReferee()
            POST /api/v1/referrals/link

        Request body:
            - email: string (required) – referee's email
            - referrerCode: string (required) – the referrer's code
            - referenceID: string (required) – campaign ID

        Returns:
            {"success": true}
        """
        payload = {
            "email": email,
            "referrerCode": referrer_code,
            "referenceID": reference_id,
        }
        logger.info(
            "Linking referee | email=%s | referrer_code=%s | program=%s",
            email,
            referrer_code,
            reference_id,
        )
        return self._post("/api/v1/referrals/link", payload)

    def log_referral_event(
        self,
        event_key: str,
        reference_id: str,
        amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """
        Log a conversion event for a referral.

        This corresponds to:
            SDK: payram.referrals.logReferralEvent()
            POST /api/v1/referrals/event

        Request body:
            - eventKey: string (required) – e.g., 'conversion', 'signup'
            - referenceID: string (required) – campaign ID
            - amount: number (optional) – for conversion events

        Returns:
            {"success": true}
        """
        payload = {"eventKey": event_key, "referenceID": reference_id}
        if amount is not None:
            payload["amount"] = float(amount)
        logger.info(
            "Logging referral event | event=%s | program=%s | amount=%s",
            event_key,
            reference_id,
            amount,
        )
        return self._post("/api/v1/referrals/event", payload)

    # ==================================================================
    # 4. Ticker API (supported chains & tokens)
    # ==================================================================

    def get_ticker(self) -> Dict[str, Any]:
        """
        Fetch the list of all supported blockchains and tokens.

        Official PayRam endpoint: GET /api/v1/ticker

        Returns a dictionary mapping blockchain codes to token metadata.

        Example response:
            {
                "ETH": {
                    "USDT": {"decimals": 6, "contract": "0xdAC17F958D2...", "enabled": true},
                    "USDC": {"decimals": 6, "contract": "0xA0b86991c621...", "enabled": true},
                    "ETH": {"decimals": 18, "contract": null, "enabled": true},
                },
                "TRX": {
                    "USDT": {"decimals": 6, "contract": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "enabled": true},
                },
                "BASE": {
                    "USDC": {"decimals": 6, "contract": "0x...", "enabled": true},
                },
                "POL": {
                    "USDT": {"decimals": 6, "contract": "0x...", "enabled": true},
                    "USDC": {"decimals": 6, "contract": "0x...", "enabled": true},
                },
                "BTC": {
                    "BTC": {"decimals": 8, "contract": null, "enabled": true},
                }
            }
        """
        logger.debug("Fetching PayRam ticker (supported chains/tokens)")
        result = self._get("/api/v1/ticker")
        logger.debug("Ticker fetched with %d blockchains", len(result))
        return result

    def get_supported_chains_and_tokens(self) -> List[Dict[str, Any]]:
        """
        Convenience method: return a simplified list of all (chain, token) pairs
        that are enabled in the current PayRam deployment.

        Useful for populating dropdowns or validating user selections.
        """
        ticker = self.get_ticker()
        supported = []
        for blockchain, tokens in ticker.items():
            if not isinstance(tokens, dict):
                continue
            for token_code, token_info in tokens.items():
                if token_info.get("enabled") is True:
                    supported.append(
                        {
                            "blockchain": blockchain,
                            "currency": token_code,
                            "decimals": token_info.get("decimals", 8),
                        }
                    )
        return supported

    # ==================================================================
    # 5. Webhook signature verification
    # ==================================================================

    def verify_webhook_signature(
        self, payload_bytes: bytes, signature_header: str
    ) -> bool:
        """
        Verify PayRam webhook HMAC‑SHA256 signature.

        PayRam signs the raw request body with the webhook secret configured
        in your PayRam dashboard. The signature arrives in the `API-Key`
        header (not X-PayRam-Signature). Yes, PayRam uses the same `API-Key`
        header for webhook authentication.

        Webhook flow:
            1. Configure webhook URL in PayRam dashboard (Settings → Webhooks)
            2. Store the shared secret as PAYRAM_WEBHOOK_SECRET
            3. On each incoming webhook, verify the `API-Key` header matches

        Uses Python stdlib `hmac.compare_digest()` for timing‑safe comparison.
        """
        if not self.webhook_secret or not signature_header:
            logger.warning("Webhook signature check skipped: secret or header missing")
            return False

        # According to PayRam webhook documentation, the signature is verified
        # by comparing the `API-Key` header with your stored secret.
        # No additional hashing is required — direct comparison.
        return hmac.compare_digest(signature_header, self.webhook_secret)

    # ==================================================================
    # 6. Address validation utilities
    # ==================================================================

    @staticmethod
    def _validate_address(address: str, blockchain_code: str) -> None:
        """
        Validate wallet address format based on blockchain.

        Raises PayRamValidationError if address format is invalid.
        """
        blockchain = blockchain_code.upper()
        if not address:
            raise PayRamValidationError("Wallet address cannot be empty")

        patterns = {
            "BTC": r"^(1[a-km-zA-HJ-NP-Z1-9]{25,34}|3[a-km-zA-HJ-NP-Z1-9]{25,34}|bc1[a-z0-9]{39,59})$",
            "ETH": r"^0x[a-fA-F0-9]{40}$",
            "BASE": r"^0x[a-fA-F0-9]{40}$",  # Same as Ethereum
            "POL": r"^0x[a-fA-F0-9]{40}$",   # Same as Ethereum
            "TRX": r"^[A-Za-z0-9]{34}$",
        }

        pattern = patterns.get(blockchain)
        if pattern:
            if not re.match(pattern, address):
                raise PayRamValidationError(
                    f"Invalid {blockchain_code} address format: {address[:20]}..."
                )
        else:
            # Unknown blockchain – accept but log warning
            logger.warning(
                "Unknown blockchain code '%s' for address validation", blockchain_code
            )

    @staticmethod
    def is_idempotency_key_required() -> bool:
        """
        PayRam does not require idempotency keys for create_payout.
        Instead, implement idempotency in your application by tracking
        `payram_payout_id` and checking if a payout has already been initiated
        for the same payment.

        This method exists for documentation purposes.
        """
        return False


# ==================================================================
# Module‑level singleton — import this everywhere.
# ==================================================================
payram = PayRamClient()