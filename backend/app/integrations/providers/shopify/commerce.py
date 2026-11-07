"""Read-only Shopify order adapter for the provider-neutral commerce contract."""

from collections.abc import Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.providers.shopify.client import (
    ShopifyAPIError,
    effective_shopify_scopes,
    fetch_order_page,
    log_shopify_api_event,
)
from app.integrations.providers.shopify.orders import lookup_authorized_order

MAX_ORDER_PAGE_SIZE = 50
ORDER_READ_SCOPES = frozenset({"read_orders"})
VERIFIED_ORDER_READ_SCOPES = frozenset({"read_orders", "read_customers"})

CommerceCredentialResolver = Callable[
    [IntegrationConnectionRef], Awaitable[tuple[str, str, frozenset[str]]]
]


class ShopifyCommerceAdapter:
    """Expose only read operations; mutations remain in approval workflows."""

    def __init__(self, resolve_credentials: CommerceCredentialResolver) -> None:
        self._resolve_credentials = resolve_credentials

    async def list_orders(
        self,
        connection: IntegrationConnectionRef,
        *,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        self._require_shopify_connection(connection)
        if not 1 <= limit <= MAX_ORDER_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_ORDER_PAGE_SIZE}")
        shop_domain, access_token, granted_scopes = await self._resolve_credentials(connection)
        self._require_scopes(granted_scopes, ORDER_READ_SCOPES)
        log_shopify_api_event(
            "commerce_order_page_started",
            organization_id=str(connection.organization_id),
            connection_id=str(connection.id),
            shop_domain=shop_domain,
            request_attempted=True,
            page_size=limit,
        )
        page = await fetch_order_page(
            shop_domain,
            access_token,
            limit=limit,
            cursor=cursor,
        )
        items = [self._map_order(node) for node in page["nodes"] if isinstance(node, dict)]
        page_info = page["page_info"]
        log_shopify_api_event(
            "commerce_order_page_completed",
            organization_id=str(connection.organization_id),
            connection_id=str(connection.id),
            shop_domain=shop_domain,
            returned_order_count=len(items),
            has_next_page=bool(page_info.get("hasNextPage")),
        )
        return {
            "items": items,
            "has_next_page": bool(page_info.get("hasNextPage")),
            "next_cursor": page_info.get("endCursor"),
        }

    async def lookup_order(
        self,
        connection: IntegrationConnectionRef,
        *,
        order_number: str,
        verified_customer_email: str,
    ) -> dict[str, Any] | None:
        """Return private order facts only after Shopify matches both identifiers.

        The caller must derive ``verified_customer_email`` from an authenticated,
        trusted customer context. A visitor-supplied email is not authorization.
        """
        self._require_shopify_connection(connection)
        normalized_order_number = order_number.strip()
        normalized_email = verified_customer_email.strip()
        if not normalized_order_number or not normalized_email:
            raise ValueError("order number and verified customer email are required")
        shop_domain, access_token, granted_scopes = await self._resolve_credentials(connection)
        self._require_scopes(granted_scopes, VERIFIED_ORDER_READ_SCOPES)
        order = await lookup_authorized_order(
            shop_domain=shop_domain,
            access_token=access_token,
            order_number=normalized_order_number,
            customer_email=normalized_email,
        )
        if order is None:
            return None
        return self._map_order(order, include_tracking=True)

    @staticmethod
    def _require_shopify_connection(connection: IntegrationConnectionRef) -> None:
        if connection.provider_id != "shopify":
            raise ShopifyAPIError("integration_provider_mismatch", status_code=400)

    @staticmethod
    def _require_scopes(granted_scopes: frozenset[str], required: frozenset[str]) -> None:
        effective_scopes = effective_shopify_scopes(granted_scopes)
        if missing := required.difference(effective_scopes):
            raise ShopifyAPIError(
                "shopify_required_scopes_missing",
                status_code=403,
                reason_code=",".join(sorted(missing)),
            )

    @classmethod
    def _map_order(cls, order: dict[str, Any], *, include_tracking: bool = False) -> dict[str, Any]:
        price_set = order.get("currentTotalPriceSet")
        shop_money = price_set.get("shopMoney") if isinstance(price_set, dict) else None
        if not isinstance(shop_money, dict):
            shop_money = {}
        mapped = {
            "id": cls._string(order.get("id")),
            "order_number": cls._string(order.get("name")),
            "created_at": cls._string(order.get("createdAt")),
            "financial_status": cls._string(order.get("displayFinancialStatus")),
            "fulfillment_status": cls._string(order.get("displayFulfillmentStatus")),
            "total_amount": cls._money(shop_money.get("amount")),
            "currency": cls._string(shop_money.get("currencyCode")),
            "cancelled_at": cls._string(order.get("cancelledAt")),
            "closed": order.get("closed") if isinstance(order.get("closed"), bool) else None,
            "tracking": cls._tracking(order) if include_tracking else [],
        }
        required_fields = ("id", "order_number", "created_at", "total_amount", "currency")
        if any(mapped[key] is None for key in required_fields):
            raise ShopifyAPIError("shopify_invalid_order_response")
        return mapped

    @staticmethod
    def _string(value: Any) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _money(value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        try:
            amount = Decimal(value)
        except InvalidOperation:
            return None
        return format(amount, "f") if amount.is_finite() else None

    @staticmethod
    def _tracking(order: dict[str, Any]) -> list[dict[str, str | None]]:
        result: list[dict[str, str | None]] = []
        fulfillments = order.get("fulfillments")
        if not isinstance(fulfillments, list):
            return result
        for fulfillment in fulfillments:
            if not isinstance(fulfillment, dict):
                continue
            tracking_info = fulfillment.get("trackingInfo")
            if not isinstance(tracking_info, list):
                continue
            for entry in tracking_info:
                if not isinstance(entry, dict):
                    continue
                url = entry.get("url")
                safe_url = None
                if isinstance(url, str):
                    try:
                        parsed_url = urlsplit(url)
                    except ValueError:
                        parsed_url = None
                    if parsed_url and parsed_url.scheme == "https" and parsed_url.hostname:
                        safe_url = url
                result.append({
                    "company": entry.get("company") if isinstance(entry.get("company"), str) else None,
                    "number": entry.get("number") if isinstance(entry.get("number"), str) else None,
                    "url": safe_url,
                })
        return result
