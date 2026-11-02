"""Shopify-specific webhook signature verification and event normalization."""

import json
from datetime import datetime

from app.integrations.core.contracts.webhooks import VerifiedWebhookEvent
from app.integrations.core.errors import IntegrationError, IntegrationErrorCode
from app.integrations.providers.shopify.catalog import _gid
from app.integrations.providers.shopify.security import (
    normalize_shop_domain,
    verify_webhook_hmac,
)

SUPPORTED_PRODUCT_TOPICS = frozenset({"products/create", "products/update", "products/delete"})


class ShopifyWebhookAdapter:
    """Verify Shopify's raw-body HMAC and normalize supported product events."""

    def verify_and_normalize(
        self,
        *,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> VerifiedWebhookEvent:
        normalized_headers = {key.casefold(): value for key, value in headers.items()}
        signature = normalized_headers.get("x-shopify-hmac-sha256", "")
        if not verify_webhook_hmac(raw_body, signature):
            raise IntegrationError(
                IntegrationErrorCode.PERMISSION_DENIED,
                retryable=False,
                provider_code="invalid_signature",
            )

        topic = normalized_headers.get("x-shopify-topic", "").casefold()
        event_id = normalized_headers.get("x-shopify-webhook-id", "")[:512]
        if topic not in SUPPORTED_PRODUCT_TOPICS or not event_id:
            raise IntegrationError(
                IntegrationErrorCode.INVALID_PAYLOAD,
                retryable=False,
                provider_code="unsupported_or_incomplete_event",
            )
        try:
            shop_domain = normalize_shop_domain(normalized_headers.get("x-shopify-shop-domain", ""))
            payload = json.loads(raw_body)
            product_id = str(payload["id"])
            if not product_id.isdigit():
                raise ValueError("invalid_product_id")
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            raise IntegrationError(
                IntegrationErrorCode.INVALID_PAYLOAD,
                retryable=False,
                provider_code="invalid_product_event",
            ) from None

        occurred_at = None
        timestamp = normalized_headers.get("x-shopify-triggered-at")
        if timestamp:
            try:
                occurred_at = datetime.fromisoformat(timestamp)
            except ValueError:
                occurred_at = None
        return VerifiedWebhookEvent(
            provider_id="shopify",
            external_account_id=shop_domain,
            external_event_id=event_id,
            event_type=topic,
            occurred_at=occurred_at,
            deduplication_key=f"shopify:{event_id}",
            normalized_payload={
                "external_product_id": _gid(product_id, "Product"),
                "shop_domain": shop_domain,
            },
        )
