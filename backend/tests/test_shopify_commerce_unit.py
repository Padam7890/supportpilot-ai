from uuid import uuid4

import pytest

from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.providers.shopify import commerce
from app.integrations.providers.shopify.client import ShopifyAPIError


def connection_ref(provider_id: str = "shopify") -> IntegrationConnectionRef:
    return IntegrationConnectionRef(
        id=uuid4(),
        organization_id=uuid4(),
        provider_id=provider_id,
        external_account_id="store.myshopify.com",
    )


@pytest.mark.anyio
async def test_list_orders_uses_tenant_connection_and_returns_pii_free_page(monkeypatch):
    seen: dict[str, object] = {}

    async def resolve(reference):
        seen["connection"] = reference
        return "store.myshopify.com", "secret-token", frozenset({"write_orders"})

    async def fetch(shop, token, *, limit, cursor):
        seen["request"] = (shop, token, limit, cursor)
        return {
            "nodes": [
                {
                    "id": "gid://shopify/Order/1",
                    "name": "#1001",
                    "createdAt": "2026-11-01T10:00:00Z",
                    "displayFinancialStatus": "PAID",
                    "displayFulfillmentStatus": "FULFILLED",
                    "currentTotalPriceSet": {"shopMoney": {"amount": "12.30", "currencyCode": "USD"}},
                    "customer": {"email": "private@example.com"},
                }
            ],
            "page_info": {"hasNextPage": True, "endCursor": "next"},
        }

    monkeypatch.setattr(commerce, "fetch_order_page", fetch)
    adapter = commerce.ShopifyCommerceAdapter(resolve)

    result = await adapter.list_orders(connection_ref(), limit=20, cursor="previous")

    assert result["has_next_page"] is True
    assert result["next_cursor"] == "next"
    assert result["items"] == [
        {
            "id": "gid://shopify/Order/1",
            "order_number": "#1001",
            "created_at": "2026-11-01T10:00:00Z",
            "financial_status": "PAID",
            "fulfillment_status": "FULFILLED",
            "total_amount": "12.30",
            "currency": "USD",
            "cancelled_at": None,
            "closed": None,
            "tracking": [],
        }
    ]
    assert "private@example.com" not in repr(result)
    assert seen["request"] == ("store.myshopify.com", "secret-token", 20, "previous")


@pytest.mark.anyio
async def test_lookup_order_requires_verified_identity_and_filters_tracking_urls(monkeypatch):
    async def resolve(_reference):
        return "store.myshopify.com", "secret-token", frozenset({"read_orders", "read_customers"})

    seen: dict[str, str] = {}

    async def lookup(**kwargs):
        seen.update({key: str(value) for key, value in kwargs.items()})
        return {
            "id": "gid://shopify/Order/2",
            "name": "#1002",
            "createdAt": "2026-11-02T10:00:00Z",
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "IN_TRANSIT",
            "cancelledAt": None,
            "closed": False,
            "currentTotalPriceSet": {"shopMoney": {"amount": "50", "currencyCode": "USD"}},
            "customer": {"email": "hidden@example.com", "displayName": "Private"},
            "fulfillments": [
                {"trackingInfo": [
                    {"company": "Carrier", "number": "TRACK123", "url": "https://carrier.example/track"},
                    {"company": "Unsafe", "number": "TRACK456", "url": "javascript:alert(1)"},
                ]}
            ],
        }

    monkeypatch.setattr(commerce, "lookup_authorized_order", lookup)
    adapter = commerce.ShopifyCommerceAdapter(resolve)

    result = await adapter.lookup_order(
        connection_ref(),
        order_number="1002",
        verified_customer_email="verified@example.com",
    )

    assert seen["order_number"] == "1002"
    assert seen["customer_email"] == "verified@example.com"
    assert result is not None
    assert result["tracking"] == [
        {"company": "Carrier", "number": "TRACK123", "url": "https://carrier.example/track"},
        {"company": "Unsafe", "number": "TRACK456", "url": None},
    ]
    assert "hidden@example.com" not in repr(result)
    assert "Private" not in repr(result)


@pytest.mark.anyio
async def test_lookup_returns_none_when_shopify_does_not_match_order_and_customer(monkeypatch):
    async def resolve(_reference):
        return "store.myshopify.com", "token", frozenset({"read_orders", "read_customers"})

    async def lookup(**_kwargs):
        return None

    monkeypatch.setattr(commerce, "lookup_authorized_order", lookup)
    adapter = commerce.ShopifyCommerceAdapter(resolve)

    result = await adapter.lookup_order(
        connection_ref(), order_number="#1003", verified_customer_email="buyer@example.com"
    )

    assert result is None


@pytest.mark.anyio
async def test_commerce_adapter_rejects_missing_scope_and_non_shopify_connections():
    async def missing_scope(_reference):
        return "store.myshopify.com", "token", frozenset({"read_orders"})

    adapter = commerce.ShopifyCommerceAdapter(missing_scope)
    with pytest.raises(ShopifyAPIError, match="shopify_required_scopes_missing"):
        await adapter.lookup_order(
            connection_ref(), order_number="#1004", verified_customer_email="buyer@example.com"
        )

    with pytest.raises(ShopifyAPIError, match="integration_provider_mismatch"):
        await adapter.list_orders(connection_ref("other"), limit=20, cursor=None)


@pytest.mark.anyio
async def test_commerce_adapter_bounds_order_page_size():
    async def resolve(_reference):
        return "store.myshopify.com", "token", frozenset({"read_orders"})

    adapter = commerce.ShopifyCommerceAdapter(resolve)
    with pytest.raises(ValueError, match="limit must be between"):
        await adapter.list_orders(connection_ref(), limit=51, cursor=None)


@pytest.mark.anyio
async def test_commerce_adapter_rejects_incomplete_shopify_order_nodes(monkeypatch):
    async def resolve(_reference):
        return "store.myshopify.com", "token", frozenset({"read_orders"})

    async def fetch(_shop, _token, *, limit, cursor):
        return {
            "nodes": [{"id": "gid://shopify/Order/5", "name": "#1005"}],
            "page_info": {"hasNextPage": False, "endCursor": None},
        }

    monkeypatch.setattr(commerce, "fetch_order_page", fetch)
    adapter = commerce.ShopifyCommerceAdapter(resolve)
    with pytest.raises(ShopifyAPIError, match="shopify_invalid_order_response"):
        await adapter.list_orders(connection_ref(), limit=10, cursor=None)
