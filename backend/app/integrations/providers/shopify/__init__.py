"""Shopify provider implementation, including commerce and OAuth concerns."""

from app.integrations.providers.shopify.actions import (
    ShopifyOrderActionError,
    cancel_shopify_order,
    check_cancellation_eligibility,
    check_cancellation_scope,
)
from app.integrations.providers.shopify.catalog import ShopifyProductCatalogAdapter
from app.integrations.providers.shopify.client import (
    ShopifyAPIError,
    effective_shopify_scopes,
    fetch_order_page,
    fetch_orders,
    graphql,
    log_shopify_api_event,
    log_shopify_event,
    request_client_credentials_token,
    request_oauth_token,
    resolve_token_scopes,
)
from app.integrations.providers.shopify.orders import (
    find_exact_order,
    lookup_authorized_order,
)
from app.integrations.providers.shopify.provider import ShopifyCatalogProvider
from app.integrations.providers.shopify.security import (
    REQUIRED_SCOPES,
    decrypt_credential,
    encrypt_credential,
    hash_oauth_state,
    make_authorization_url,
    normalize_shop_domain,
    validate_callback_timestamp,
    verify_callback_hmac,
    verify_webhook_hmac,
)

__all__ = [
    "REQUIRED_SCOPES",
    "ShopifyAPIError",
    "ShopifyCatalogProvider",
    "ShopifyOrderActionError",
    "ShopifyProductCatalogAdapter",
    "cancel_shopify_order",
    "check_cancellation_eligibility",
    "check_cancellation_scope",
    "decrypt_credential",
    "effective_shopify_scopes",
    "encrypt_credential",
    "fetch_order_page",
    "fetch_orders",
    "find_exact_order",
    "graphql",
    "hash_oauth_state",
    "log_shopify_api_event",
    "log_shopify_event",
    "lookup_authorized_order",
    "make_authorization_url",
    "normalize_shop_domain",
    "request_client_credentials_token",
    "request_oauth_token",
    "resolve_token_scopes",
    "validate_callback_timestamp",
    "verify_callback_hmac",
    "verify_webhook_hmac",
]
