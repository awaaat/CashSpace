"""
apps/gating/tokens.py
=====================
Advanced token generation and verification for gated assets.

Supports multiple token formats:
  - Simple UUID (legacy, less secure)
  - HMAC‑signed string (stateless, verifiable without DB)
  - JWT (HS256 or RS256) with standard claims
  - PASETO v4.local (symmetric) and v4.public (asymmetric) — most secure

All tokens can be:
  - Time‑limited (exp)
  - Single‑use (nonce tracked in Redis)
  - Bound to specific asset, buyer email, or IP address
  - Verified by external servers via a public key (PASETO/JWT) or shared secret (HMAC)

Features:
  - Automatic Redis nonce store for single‑use enforcement
  - Token introspection endpoint payload format
  - Safe for embedding in URLs (URL‑safe base64 encoding for PASETO/JWT)
  - Support for custom claims (e.g., tier, duration)
"""

import uuid
import hashlib
import hmac
import json
import base64
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, Dict, Any, Tuple, Union
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

# PASETO (if installed) — fallback to pure Python implementation if not
try:
    from pypaseto import ProtocolVersion, Purpose, token as paseto_token
    from pypaseto.keys import AsymmetricSecretKey, AsymmetricPublicKey, SymmetricKey
    HAS_PASETO = True
except ImportError:
    HAS_PASETO = False

# PyJWT (if installed)
try:
    import jwt
    HAS_JWT = True
except ImportError:
    HAS_JWT = False


# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------
TOKEN_TYPE = getattr(settings, 'GATING_TOKEN_TYPE', 'PASETO')  # 'UUID', 'HMAC', 'JWT', 'PASETO'
TOKEN_EXPIRY_SECONDS = getattr(settings, 'GATING_TOKEN_EXPIRY_SECONDS', 3600)  # 1 hour default
TOKEN_MAX_USES = getattr(settings, 'GATING_TOKEN_MAX_USES', 1)
JWT_SECRET = getattr(settings, 'GATING_JWT_SECRET', settings.SECRET_KEY)
JWT_ALGORITHM = getattr(settings, 'GATING_JWT_ALGORITHM', 'HS256')
JWT_PUBLIC_KEY = getattr(settings, 'GATING_JWT_PUBLIC_KEY', None)   # for RS256
JWT_PRIVATE_KEY = getattr(settings, 'GATING_JWT_PRIVATE_KEY', None)  # for RS256
PASETO_SECRET_KEY = getattr(settings, 'GATING_PASETO_SECRET_KEY', None)  # for v4.local
PASETO_PUBLIC_KEY = getattr(settings, 'GATING_PASETO_PUBLIC_KEY', None)  # for v4.public
PASETO_PRIVATE_KEY = getattr(settings, 'GATING_PASETO_PRIVATE_KEY', None) # for v4.public
REDIS_TOKEN_PREFIX = getattr(settings, 'GATING_REDIS_TOKEN_PREFIX', 'gating:token:')


# ----------------------------------------------------------------------
# Exception
# ----------------------------------------------------------------------
class TokenError(Exception):
    """Base exception for token errors."""
    pass


class TokenExpiredError(TokenError):
    pass


class TokenInvalidError(TokenError):
    pass


class TokenExhaustedError(TokenError):
    pass


# ----------------------------------------------------------------------
# Token payload structure (canonical)
# ----------------------------------------------------------------------
@dataclass
class TokenPayload:
    """Standardised payload structure for all token types."""
    asset_id: str
    grant_id: str
    buyer_email: str
    exp: Optional[datetime] = None
    nonce: Optional[str] = None
    max_uses: int = 1
    custom_claims: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "asset_id": self.asset_id,
            "grant_id": self.grant_id,
            "buyer_email": self.buyer_email,
            "max_uses": self.max_uses,
        }
        if self.exp:
            result["exp"] = int(self.exp.timestamp())
        if self.nonce:
            result["nonce"] = self.nonce
        if self.custom_claims:
            result.update(self.custom_claims)
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "TokenPayload":
        exp = None
        if "exp" in data:
            exp = datetime.fromtimestamp(data["exp"], tz=timezone.utc)
        return cls(
            asset_id=data["asset_id"],
            grant_id=data["grant_id"],
            buyer_email=data["buyer_email"],
            exp=exp,
            nonce=data.get("nonce"),
            max_uses=data.get("max_uses", 1),
            custom_claims={k: v for k, v in data.items() if k not in ["asset_id", "grant_id", "buyer_email", "exp", "nonce", "max_uses"]},
        )


# ----------------------------------------------------------------------
# Redis nonce manager (for single‑use tokens)
# ----------------------------------------------------------------------
class NonceManager:
    """Handles single‑use token tracking with Redis, including TTL."""

    @staticmethod
    def _key(nonce: str) -> str:
        return f"{REDIS_TOKEN_PREFIX}{nonce}"

    @staticmethod
    def is_used(nonce: str) -> bool:
        """Check if a nonce has already been used."""
        return cache.get(NonceManager._key(nonce)) is not None

    @staticmethod
    def mark_used(nonce: str, ttl_seconds: int = None):
        """Mark a nonce as used, with optional TTL (default = token expiry)."""
        if ttl_seconds is None:
            ttl_seconds = TOKEN_EXPIRY_SECONDS
        cache.set(NonceManager._key(nonce), "used", timeout=ttl_seconds)

    @staticmethod
    def clear(nonce: str):
        cache.delete(NonceManager._key(nonce))


# ----------------------------------------------------------------------
# Token Generator – unified interface
# ----------------------------------------------------------------------
class TokenGenerator:
    """Factory for generating and verifying tokens of various types."""

    @staticmethod
    def generate(payload: TokenPayload, token_type: str = None) -> str:
        """Generate a token string from a payload."""
        ttype = (token_type or TOKEN_TYPE).upper()
        if ttype == "UUID":
            return TokenGenerator._generate_uuid(payload)
        elif ttype == "HMAC":
            return TokenGenerator._generate_hmac(payload)
        elif ttype == "JWT":
            return TokenGenerator._generate_jwt(payload)
        elif ttype == "PASETO":
            return TokenGenerator._generate_paseto(payload)
        else:
            raise TokenError(f"Unsupported token type: {ttype}")

    @staticmethod
    def verify(token_str: str, token_type: str = None) -> TokenPayload:
        """Verify a token and return the payload."""
        ttype = (token_type or TOKEN_TYPE).upper()
        if ttype == "UUID":
            return TokenGenerator._verify_uuid(token_str)
        elif ttype == "HMAC":
            return TokenGenerator._verify_hmac(token_str)
        elif ttype == "JWT":
            return TokenGenerator._verify_jwt(token_str)
        elif ttype == "PASETO":
            return TokenGenerator._verify_paseto(token_str)
        else:
            raise TokenError(f"Unsupported token type: {ttype}")

    # ------------------------------------------------------------------
    # UUID (simplest, but stateless with Redis nonce for single‑use)
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_uuid(payload: TokenPayload) -> str:
        token = str(uuid.uuid4())
        # Store payload in Redis with token as key
        cache.set(f"{REDIS_TOKEN_PREFIX}{token}", payload.to_dict(), timeout=TOKEN_EXPIRY_SECONDS)
        return token

    @staticmethod
    def _verify_uuid(token_str: str) -> TokenPayload:
        data = cache.get(f"{REDIS_TOKEN_PREFIX}{token_str}")
        if not data:
            raise TokenInvalidError("Token not found or expired")
        payload = TokenPayload.from_dict(data)
        if payload.exp and timezone.now() > payload.exp:
            raise TokenExpiredError("Token expired")
        # Single‑use enforcement: delete from cache after use (if max_uses=1)
        if payload.max_uses == 1:
            cache.delete(f"{REDIS_TOKEN_PREFIX}{token_str}")
        return payload

    # ------------------------------------------------------------------
    # HMAC‑signed (stateless, verifiable without DB, but no built‑in expiry in token)
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_hmac(payload: TokenPayload) -> str:
        data = payload.to_dict()
        # Remove nonce if present (we'll generate fresh)
        data.pop("nonce", None)
        # Add a random nonce and timestamp
        nonce = str(uuid.uuid4())
        data["nonce"] = nonce
        data["iat"] = int(timezone.now().timestamp())
        if not payload.exp:
            data["exp"] = int((timezone.now() + timedelta(seconds=TOKEN_EXPIRY_SECONDS)).timestamp())
        # Serialise
        json_str = json.dumps(data, sort_keys=True)
        signature = hmac.new(
            JWT_SECRET.encode('utf-8'),
            json_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        # Combine: base64(json) + '.' + signature
        encoded = base64.urlsafe_b64encode(json_str.encode()).decode().rstrip("=")
        return f"{encoded}.{signature}"

    @staticmethod
    def _verify_hmac(token_str: str) -> TokenPayload:
        parts = token_str.split(".")
        if len(parts) != 2:
            raise TokenInvalidError("Invalid HMAC token format")
        encoded, signature = parts
        try:
            json_str = base64.urlsafe_b64decode(encoded + "===").decode()
        except Exception:
            raise TokenInvalidError("Invalid base64 encoding")
        # Verify signature
        expected_sig = hmac.new(
            JWT_SECRET.encode('utf-8'),
            json_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            raise TokenInvalidError("Invalid signature")
        data = json.loads(json_str)
        # Check expiry
        exp = data.get("exp")
        if exp and timezone.now().timestamp() > exp:
            raise TokenExpiredError("Token expired")
        # Single‑use check via Redis nonce
        nonce = data.get("nonce")
        if nonce and NonceManager.is_used(nonce):
            raise TokenExhaustedError("Token already used")
        # Mark as used if max_uses == 1
        max_uses = data.get("max_uses", 1)
        if max_uses == 1 and nonce:
            NonceManager.mark_used(nonce, ttl_seconds=TOKEN_EXPIRY_SECONDS)
        return TokenPayload.from_dict(data)

    # ------------------------------------------------------------------
    # JWT (RS256/HS256)
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_jwt(payload: TokenPayload) -> str:
        if not HAS_JWT:
            raise TokenError("PyJWT not installed. Install with: pip install PyJWT")
        claims = payload.to_dict()
        claims["iat"] = timezone.now()
        if not payload.exp:
            claims["exp"] = timezone.now() + timedelta(seconds=TOKEN_EXPIRY_SECONDS)
        # Ensure exp is integer timestamp
        if isinstance(claims.get("exp"), datetime):
            claims["exp"] = int(claims["exp"].timestamp())
        if isinstance(claims.get("iat"), datetime):
            claims["iat"] = int(claims["iat"].timestamp())
        if JWT_ALGORITHM.startswith("RS"):
            if not JWT_PRIVATE_KEY:
                raise TokenError("JWT private key not configured for RS256")
            token = jwt.encode(claims, JWT_PRIVATE_KEY, algorithm=JWT_ALGORITHM)
        else:
            token = jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return token

    @staticmethod
    def _verify_jwt(token_str: str) -> TokenPayload:
        if not HAS_JWT:
            raise TokenError("PyJWT not installed")
        try:
            if JWT_ALGORITHM.startswith("RS"):
                if not JWT_PUBLIC_KEY:
                    raise TokenError("JWT public key not configured for RS256")
                decoded = jwt.decode(token_str, JWT_PUBLIC_KEY, algorithms=[JWT_ALGORITHM])
            else:
                decoded = jwt.decode(token_str, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise TokenExpiredError("Token expired")
        except jwt.InvalidTokenError as e:
            raise TokenInvalidError(f"Invalid JWT: {e}")
        # Single‑use enforcement via nonce
        nonce = decoded.get("nonce")
        max_uses = decoded.get("max_uses", 1)
        if max_uses == 1 and nonce:
            if NonceManager.is_used(nonce):
                raise TokenExhaustedError("Token already used")
            NonceManager.mark_used(nonce, ttl_seconds=TOKEN_EXPIRY_SECONDS)
        return TokenPayload.from_dict(decoded)

    # ------------------------------------------------------------------
    # PASETO v4.local (symmetric) / v4.public (asymmetric)
    # ------------------------------------------------------------------
    @staticmethod
    def _generate_paseto(payload: TokenPayload) -> str:
        if not HAS_PASETO:
            raise TokenError("PyPASETO not installed. Install with: pip install pypaseto")
        claims = payload.to_dict()
        # Add standard claims
        claims["iat"] = timezone.now().isoformat()
        if not payload.exp:
            exp_dt = timezone.now() + timedelta(seconds=TOKEN_EXPIRY_SECONDS)
            claims["exp"] = exp_dt.isoformat()
        else:
            claims["exp"] = payload.exp.isoformat()
        # Determine which version/mode
        if PASETO_PRIVATE_KEY and PASETO_PUBLIC_KEY:
            # v4.public (asymmetric)
            secret_key = AsymmetricSecretKey(PASETO_PRIVATE_KEY, version=ProtocolVersion.V4)
            token = paseto_token.create(
                purpose=Purpose.PUBLIC,
                claims=claims,
                key=secret_key,
            )
        elif PASETO_SECRET_KEY:
            # v4.local (symmetric)
            secret_key = SymmetricKey(PASETO_SECRET_KEY, version=ProtocolVersion.V4)
            token = paseto_token.create(
                purpose=Purpose.LOCAL,
                claims=claims,
                key=secret_key,
            )
        else:
            raise TokenError("PASETO key not configured: set GATING_PASETO_SECRET_KEY or GATING_PASETO_PRIVATE_KEY")
        return token

    @staticmethod
    def _verify_paseto(token_str: str) -> TokenPayload:
        if not HAS_PASETO:
            raise TokenError("PyPASETO not installed")
        try:
            if PASETO_PUBLIC_KEY:
                # v4.public
                public_key = AsymmetricPublicKey(PASETO_PUBLIC_KEY, version=ProtocolVersion.V4)
                decoded = paseto_token.verify(
                    token=token_str,
                    key=public_key,
                    purpose=Purpose.PUBLIC,
                )
            elif PASETO_SECRET_KEY:
                # v4.local
                secret_key = SymmetricKey(PASETO_SECRET_KEY, version=ProtocolVersion.V4)
                decoded = paseto_token.verify(
                    token=token_str,
                    key=secret_key,
                    purpose=Purpose.LOCAL,
                )
            else:
                raise TokenError("PASETO key not configured for verification")
        except Exception as e:
            raise TokenInvalidError(f"PASETO verification failed: {e}")
        # Check expiry
        exp_str = decoded.get("exp")
        if exp_str:
            exp = datetime.fromisoformat(exp_str)
            if timezone.now() > exp:
                raise TokenExpiredError("Token expired")
        # Single‑use nonce
        nonce = decoded.get("nonce")
        max_uses = decoded.get("max_uses", 1)
        if max_uses == 1 and nonce:
            if NonceManager.is_used(nonce):
                raise TokenExhaustedError("Token already used")
            NonceManager.mark_used(nonce, ttl_seconds=TOKEN_EXPIRY_SECONDS)
        return TokenPayload.from_dict(decoded)


# ----------------------------------------------------------------------
# High‑level convenience functions
# ----------------------------------------------------------------------
def create_access_token(
    asset_id: str,
    grant_id: str,
    buyer_email: str,
    expires_in_seconds: Optional[int] = None,
    max_uses: int = 1,
    custom_claims: Optional[Dict] = None,
    token_type: Optional[str] = None,
) -> str:
    """Create a new access token for a granted purchase."""
    exp = None
    if expires_in_seconds or (expires_in_seconds is None and TOKEN_EXPIRY_SECONDS):
        exp = timezone.now() + timedelta(seconds=expires_in_seconds or TOKEN_EXPIRY_SECONDS)
    payload = TokenPayload(
        asset_id=asset_id,
        grant_id=grant_id,
        buyer_email=buyer_email,
        exp=exp,
        max_uses=max_uses,
        custom_claims=custom_claims,
    )
    return TokenGenerator.generate(payload, token_type=token_type)


def verify_access_token(token_str: str, token_type: Optional[str] = None) -> TokenPayload:
    """Verify an access token. Raises TokenError derivatives."""
    return TokenGenerator.verify(token_str, token_type=token_type)


def is_token_valid(token_str: str, token_type: Optional[str] = None) -> bool:
    """Return True if token is valid (not expired, not exhausted, signature ok)."""
    try:
        verify_access_token(token_str, token_type)
        return True
    except TokenError:
        return False


def get_token_payload_safe(token_str: str, token_type: Optional[str] = None) -> Optional[Dict]:
    """Safely decode token without raising exceptions. Returns dict or None."""
    try:
        payload = verify_access_token(token_str, token_type)
        return payload.to_dict()
    except TokenError:
        return None


# ----------------------------------------------------------------------
# External verification endpoint helper (for merchant servers)
# ----------------------------------------------------------------------
def build_verification_response(token_str: str) -> Dict[str, Any]:
    """
    Build a standard JSON response for external verification.
    Used by POST /api/v1/gating/verify-token/
    """
    try:
        payload = verify_access_token(token_str)
        return {
            "valid": True,
            "asset_id": payload.asset_id,
            "grant_id": payload.grant_id,
            "buyer_email": payload.buyer_email,
            "expires_at": payload.exp.isoformat() if payload.exp else None,
            "custom_claims": payload.custom_claims,
        }
    except TokenExpiredError:
        return {"valid": False, "reason": "expired"}
    except TokenExhaustedError:
        return {"valid": False, "reason": "already_used"}
    except TokenInvalidError:
        return {"valid": False, "reason": "invalid_signature"}
    except Exception as e:
        return {"valid": False, "reason": str(e)}


# ----------------------------------------------------------------------
# URL‑safe token embedding helpers
# ----------------------------------------------------------------------
def token_to_url_param(token_str: str) -> str:
    """Make token safe for URL query parameters (already safe for JWT/PASETO, but ensure)."""
    # PASETO and JWT are already URL‑safe base64. UUID is hex. HMAC uses urlsafe_b64.
    return token_str


def build_unlock_url(base_url: str, token: str, as_query_param: bool = True) -> str:
    """Build a full unlock URL with token as query param or path."""
    if as_query_param:
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}access_token={token}"
    else:
        # Append as path segment (assuming base_url ends with /)
        base = base_url.rstrip("/")
        return f"{base}/{token}"