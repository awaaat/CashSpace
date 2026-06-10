# apps/core/exceptions.py
# Enterprise-grade exception classes for CashSpace.
#
# Provides a clear hierarchy of custom exceptions for different domains:
#   - PayRam integration errors
#   - Payment processing errors
#   - Account validation errors
#   - Business logic violations (commission, limits, etc.)
#   - External service failures (rates, webhooks)
#
# These exceptions can be caught in views and mapped to appropriate
# HTTP responses (400, 402, 403, 502, etc.) using DRF's exception handler.

from typing import Any, Dict, Optional


# ==================================================================
# Base Exception
# ==================================================================

class CashSpaceException(Exception):
    """Base exception for all CashSpace‑specific errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code or self.__class__.__name__
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a structured dict for API error responses."""
        result = {"code": self.code, "message": self.message}
        if self.details:
            result["details"] = self.details
        return result


# ==================================================================
# Account & User Exceptions
# ==================================================================

class AccountError(CashSpaceException):
    """Base for all account‑related errors."""
    pass


class WalletError(AccountError):
    """User wallet (crypto address) issues."""
    pass


class InsufficientWalletError(WalletError):
    """User has no wallet configured for the requested blockchain/currency."""
    pass


class InvalidWalletAddressError(WalletError):
    """Address format does not match blockchain requirements."""
    pass


class UserLockedError(AccountError):
    """Account is temporarily locked due to failed login attempts."""
    pass


class EmailNotVerifiedError(AccountError):
    """User hasn't verified their email address."""
    pass


class KYCRequiredError(AccountError):
    """User must complete KYC before performing this action."""
    pass


# ==================================================================
# Payment Exceptions
# ==================================================================

class PaymentError(CashSpaceException):
    """Base for all payment‑processing errors."""
    pass


class InsufficientPaymentAmountError(PaymentError):
    """Amount is below the minimum allowed."""
    pass


class PaymentLimitExceededError(PaymentError):
    """Daily or hourly limit reached."""
    pass


class PaymentAlreadyProcessedError(PaymentError):
    """Payment is in a terminal state and cannot be modified."""
    pass


class PaymentNotFoundError(PaymentError):
    """Requested payment does not exist or does not belong to user."""
    pass


class CommissionCalculationError(PaymentError):
    """Failed to compute commission due to invalid inputs."""
    pass


# ==================================================================
# PayRam Integration Exceptions
# ==================================================================

class PayRamIntegrationError(CashSpaceException):
    """Base for all PayRam API errors."""
    pass


class PayRamConnectionError(PayRamIntegrationError):
    """Unable to reach PayRam server (network issue)."""
    pass


class PayRamAuthenticationError(PayRamIntegrationError):
    """API key is invalid or missing."""
    pass


class PayRamNotFoundError(PayRamIntegrationError):
    """Requested resource (payment, payout) not found in PayRam."""
    pass


class PayRamValidationError(PayRamIntegrationError):
    """PayRam rejected the request due to invalid parameters."""
    pass


class PayRamRateLimitError(PayRamIntegrationError):
    """Hit PayRam's rate limit."""
    pass


class PayRamTimeoutError(PayRamIntegrationError):
    """PayRam request exceeded timeout."""
    pass


# ==================================================================
# Exchange Rate & Ticker Exceptions
# ==================================================================

class ExchangeRateError(CashSpaceException):
    """Failed to fetch or compute exchange rate."""
    pass


class UnsupportedCurrencyPairError(ExchangeRateError):
    """The requested blockchain/currency pair is not supported."""
    pass


# ==================================================================
# Business Logic Exceptions
# ==================================================================

class BusinessRuleViolation(CashSpaceException):
    """Generic business rule violation (e.g., commission out of range)."""
    pass


class CommissionRateInvalidError(BusinessRuleViolation):
    """Commission rate not between 0 and 1."""
    pass


class WebhookVerificationError(CashSpaceException):
    """Webhook signature validation failed."""
    pass


# ==================================================================
# Utility: map exception to HTTP status code (for DRF exception handler)
# ==================================================================

def exception_to_http_status(exc: CashSpaceException) -> int:
    """
    Map a CashSpaceException subclass to an appropriate HTTP status code.
    Used in custom DRF exception handler.
    """
    mapping = {
        # Authentication / Authorization
        UserLockedError: 423,           # Locked
        EmailNotVerifiedError: 403,     # Forbidden until verified
        KYCRequiredError: 403,

        # Wallet / Account
        WalletError: 400,
        InvalidWalletAddressError: 400,
        InsufficientWalletError: 404,

        # Payment
        PaymentNotFoundError: 404,
        InsufficientPaymentAmountError: 400,
        PaymentLimitExceededError: 429,
        PaymentAlreadyProcessedError: 409,
        CommissionCalculationError: 500,

        # PayRam integration (external service)
        PayRamConnectionError: 502,
        PayRamAuthenticationError: 401,
        PayRamNotFoundError: 404,
        PayRamValidationError: 400,
        PayRamRateLimitError: 429,
        PayRamTimeoutError: 504,
        PayRamIntegrationError: 502,

        # Exchange rate
        ExchangeRateError: 503,
        UnsupportedCurrencyPairError: 400,

        # Webhook
        WebhookVerificationError: 401,

        # Default
        BusinessRuleViolation: 422,
    }

    for exc_type, status in mapping.items():
        if isinstance(exc, exc_type):
            return status

    return 400  # Default bad request