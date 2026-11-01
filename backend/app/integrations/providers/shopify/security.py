"""Security helpers for Shopify's standalone-app OAuth flow."""

import base64
import hashlib
import hmac
import re
import time
from collections.abc import Sequence
from urllib.parse import urlencode

from app.core.config import settings

__all__ = [
    "PRODUCT_CATALOG_SCOPES",
    "REQUIRED_SCOPES",
    "SHOP_DOMAIN",
    "decrypt_credential",
    "encrypt_credential",
    "hash_oauth_state",
    "make_authorization_url",
    "normalize_shop_domain",
    "validate_callback_timestamp",
    "verify_callback_hmac",
    "verify_webhook_hmac",
]

SHOP_DOMAIN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]*\.myshopify\.com$")
REQUIRED_SCOPES = ("read_orders", "read_customers")
PRODUCT_CATALOG_SCOPES = ("read_products",)


def normalize_shop_domain(shop: str) -> str:
    domain = shop.strip().lower().rstrip(".")
    if not SHOP_DOMAIN.fullmatch(domain):
        raise ValueError("Enter a valid myshopify.com store domain")
    return domain


def hash_oauth_state(state: str) -> str:
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def verify_callback_hmac(query_items: Sequence[tuple[str, str]], supplied: str) -> bool:
    if settings.shopify_client_secret is None or not re.fullmatch(r"[0-9a-fA-F]{64}", supplied):
        return False
    pairs = [(key, value) for key, value in query_items if key != "hmac"]
    canonical = "&".join(f"{key}={value}" for key, value in sorted(pairs))
    expected = hmac.new(
        settings.shopify_client_secret.get_secret_value().encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, supplied.lower())


def verify_webhook_hmac(raw_body: bytes, supplied: str) -> bool:
    """Verify Shopify's base64 HMAC over the exact raw request body."""
    if settings.shopify_client_secret is None or not supplied:
        return False
    expected = base64.b64encode(
        hmac.new(
            settings.shopify_client_secret.get_secret_value().encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).digest()
    ).decode("ascii")
    return hmac.compare_digest(expected, supplied)


def validate_callback_timestamp(timestamp: str, *, max_age_seconds: int = 600) -> bool:
    try:
        supplied = int(timestamp)
    except (TypeError, ValueError):
        return False
    return abs(int(time.time()) - supplied) <= max_age_seconds


def make_authorization_url(shop: str, state: str) -> str:
    if not settings.shopify_client_id or not settings.shopify_redirect_uri:
        raise RuntimeError("Shopify OAuth is not configured")
    params = urlencode(
        {
            "client_id": settings.shopify_client_id,
            "scope": ",".join((*REQUIRED_SCOPES, *PRODUCT_CATALOG_SCOPES)),
            "redirect_uri": settings.shopify_redirect_uri,
            "state": state,
        }
    )
    return f"https://{normalize_shop_domain(shop)}/admin/oauth/authorize?{params}"


def encrypt_credential(value: str) -> str:
    if settings.shopify_encryption_key is None:
        raise RuntimeError("Shopify credential encryption is not configured")
    from cryptography.fernet import Fernet

    try:
        cipher = Fernet(settings.shopify_encryption_key.get_secret_value().encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise RuntimeError("Shopify credential encryption key is invalid") from exc
    return cipher.encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_credential(value: str) -> str:
    if settings.shopify_encryption_key is None:
        raise RuntimeError("Shopify credential encryption is not configured")
    from cryptography.fernet import Fernet, InvalidToken

    try:
        cipher = Fernet(settings.shopify_encryption_key.get_secret_value().encode("ascii"))
        return cipher.decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeEncodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Stored Shopify credentials cannot be decrypted") from exc
