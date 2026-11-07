from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.core import IntegrationCapability, ProductCatalogCapability
from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.providers.shopify import catalog as shopify_catalog
from app.integrations.providers.shopify.client import ShopifyAPIError, effective_shopify_scopes
from app.integrations.providers.shopify.provider import ShopifyCatalogProvider


def test_product_normalization_keeps_price_on_variant_and_strips_html():
    product = shopify_catalog.map_product(
        {
            "id": "gid://shopify/Product/10",
            "title": "Canvas bag",
            "descriptionHtml": "<p>Strong <b>canvas</b> bag</p>",
            "vendor": "Example",
            "productType": "Bags",
            "status": "ACTIVE",
            "updatedAt": "2026-10-31T10:00:00Z",
            "onlineStoreUrl": "https://shop.example/products/canvas-bag",
            "images": {"nodes": [{"url": "https://cdn.example/bag.png", "altText": "Bag"}]},
            "variants": {
                "nodes": [
                    {
                        "id": "gid://shopify/ProductVariant/20",
                        "title": "Blue / Large",
                        "sku": "BAG-BL-L",
                        "price": {"amount": "19.9500", "currencyCode": "USD"},
                        "compareAtPrice": {"amount": "25.00", "currencyCode": "USD"},
                        "availableForSale": True,
                        "selectedOptions": [{"name": "Color", "value": "Blue"}],
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        }
    )

    assert product.description == "Strong canvas bag"
    assert str(product.canonical_url) == "https://shop.example/products/canvas-bag"
    assert len(product.variants) == 1
    assert str(product.variants[0].price) == "19.9500"
    assert str(product.variants[0].compare_at_price) == "25.00"
    assert product.variants[0].currency == "USD"
    assert product.variants[0].attributes == {"Color": "Blue"}


def test_shopify_2026_money_scalars_use_verified_shop_currency():
    product = shopify_catalog.map_product(
        {
            "id": "gid://shopify/Product/11",
            "title": "Wool scarf",
            "status": "ACTIVE",
            "variants": {
                "nodes": [
                    {
                        "id": "gid://shopify/ProductVariant/21",
                        "title": "Default",
                        "price": "1499.50",
                        "compareAtPrice": "1799.00",
                        "availableForSale": True,
                    }
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            },
        },
        default_currency="NPR",
    )

    assert str(product.variants[0].price) == "1499.50"
    assert str(product.variants[0].compare_at_price) == "1799.00"
    assert product.variants[0].currency == "NPR"
    assert "price { amount currencyCode }" not in shopify_catalog.PRODUCTS_QUERY
    assert "shop { currencyCode }" in shopify_catalog.PRODUCTS_QUERY


@pytest.mark.anyio
async def test_shopify_product_pagination_normalizes_all_pages(monkeypatch, caplog):
    calls = []

    async def fake_graphql(_shop, _token, _query, variables, **_kwargs):
        calls.append(variables)
        page_number = len(calls)
        return {
            "products": {
                "nodes": [
                    {
                        "id": f"gid://shopify/Product/{page_number}",
                        "title": f"Product {page_number}",
                        "status": "ACTIVE",
                        "variants": {"nodes": [], "pageInfo": {"hasNextPage": False}},
                    }
                ],
                "pageInfo": {
                    "hasNextPage": page_number == 1,
                    "endCursor": "cursor-page-2" if page_number == 1 else None,
                },
            }
        }

    monkeypatch.setattr(shopify_catalog, "graphql", fake_graphql)
    from app.integrations.providers.shopify import client as shopify_client

    connection = IntegrationConnectionRef(
        id=uuid4(),
        organization_id=uuid4(),
        provider_id="shopify",
        external_account_id="demo.myshopify.com",
    )

    async def credentials(_connection):
        return "demo.myshopify.com", "should-not-be-logged"

    adapter = shopify_catalog.ShopifyProductCatalogAdapter(credentials)
    with caplog.at_level("INFO", logger=shopify_client.__name__):
        first = await adapter.list_products(connection, limit=20, cursor=None)
        second = await adapter.list_products(connection, limit=20, cursor=first.next_cursor)

    assert first.has_more is True
    assert first.next_cursor == "cursor-page-2"
    assert second.has_more is False
    assert [item.title for item in first.items + second.items] == ["Product 1", "Product 2"]
    assert calls[0]["after"] is None
    assert calls[1]["after"] == "cursor-page-2"
    assert caplog.text.count('"event": "catalog_products_response"') == 2
    assert '"products_returned": 1' in caplog.text
    assert '"has_more": true' in caplog.text
    assert '"has_more": false' in caplog.text
    assert "should-not-be-logged" not in caplog.text
    assert "Product 1" not in caplog.text


@pytest.mark.anyio
async def test_shopify_empty_product_catalog_is_a_valid_empty_page(monkeypatch):
    async def fake_graphql(_shop, _token, _query, _variables, **_kwargs):
        return {
            "products": {
                "nodes": [],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }

    monkeypatch.setattr(shopify_catalog, "graphql", fake_graphql)
    connection = IntegrationConnectionRef(
        id=uuid4(),
        organization_id=uuid4(),
        provider_id="shopify",
        external_account_id="empty-demo.myshopify.com",
    )
    adapter = shopify_catalog.ShopifyProductCatalogAdapter(
        lambda _connection: _credentials("empty-demo.myshopify.com", "private-token")
    )

    page = await adapter.list_products(connection, limit=20, cursor=None)

    assert page.items == []
    assert page.has_more is False
    assert page.next_cursor is None


@pytest.mark.anyio
async def test_shopify_adapter_propagates_safe_api_failure(monkeypatch):
    async def fail(*_args, **_kwargs):
        raise ShopifyAPIError("shopify_unavailable", status_code=503)

    monkeypatch.setattr(shopify_catalog, "graphql", fail)
    connection = IntegrationConnectionRef(
        id=uuid4(),
        organization_id=uuid4(),
        provider_id="shopify",
        external_account_id="demo.myshopify.com",
    )
    adapter = shopify_catalog.ShopifyProductCatalogAdapter(
        lambda _connection: _credentials("demo.myshopify.com", "private-token")
    )
    with pytest.raises(ShopifyAPIError, match="shopify_unavailable"):
        await adapter.list_products(connection, limit=10, cursor=None)


@pytest.mark.anyio
async def test_catalog_credentials_reject_installation_for_a_different_shop(monkeypatch):
    from app.services import catalog as catalog_service

    connection = IntegrationConnectionRef(
        id=uuid4(),
        organization_id=uuid4(),
        provider_id="shopify",
        external_account_id="expected-shop.myshopify.com",
    )
    other_shop_installation = SimpleNamespace(
        shop_domain="different-shop.myshopify.com",
        disconnected_at=None,
        access_token_encrypted="must-not-be-used",
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def scalar(self, _statement):
            return other_shop_installation

    async def no_op_tenant_context(_session, _organization_id):
        return None

    monkeypatch.setattr(catalog_service, "SessionLocal", FakeSession)
    monkeypatch.setattr(catalog_service, "set_tenant_context", no_op_tenant_context)

    with pytest.raises(ShopifyAPIError, match="catalog_not_connected"):
        await catalog_service.resolve_shopify_credentials(connection)


@pytest.mark.anyio
async def test_shopify_direct_current_price_lookup_is_variant_scoped(monkeypatch):
    async def fake_graphql(_shop, _token, _query, _variables):
        return {
            "productVariant": {
                "id": "gid://shopify/ProductVariant/20",
                "title": "Blue",
                "price": {"amount": "21.25", "currencyCode": "USD"},
                "compareAtPrice": {"amount": "25.00", "currencyCode": "USD"},
                "availableForSale": True,
                "updatedAt": "2026-10-31T10:00:00Z",
            }
        }

    monkeypatch.setattr(shopify_catalog, "graphql", fake_graphql)
    connection = IntegrationConnectionRef(
        id=uuid4(),
        organization_id=uuid4(),
        provider_id="shopify",
        external_account_id="demo.myshopify.com",
    )
    adapter = shopify_catalog.ShopifyProductCatalogAdapter(
        lambda _connection: _credentials("demo.myshopify.com", "private-token")
    )
    price = await adapter.get_current_price(
        connection,
        external_variant_id="gid://shopify/ProductVariant/20",
    )

    assert price is not None
    assert str(price.price) == "21.25"
    assert str(price.compare_at_price) == "25.00"
    assert price.currency == "USD"


async def _credentials(shop: str, token: str) -> tuple[str, str]:
    return shop, token


def test_shopify_provider_exposes_catalog_and_read_only_commerce_capabilities():
    async def commerce_credentials(_connection):
        return "demo.myshopify.com", "token", frozenset({"read_orders", "read_customers"})

    provider = ShopifyCatalogProvider(
        lambda _connection: _credentials("demo.myshopify.com", "token"),
        commerce_credentials,
    )

    assert IntegrationCapability.PRODUCT_CATALOG in provider.descriptor.capabilities
    capability = provider.get_capability(IntegrationCapability.PRODUCT_CATALOG)
    assert isinstance(capability, ProductCatalogCapability)
    assert provider.get_capability(IntegrationCapability.CART) is None


def test_product_read_scope_is_independent_of_existing_order_read_requirements():
    assert effective_shopify_scopes(["write_products"]) == {"write_products", "read_products"}
    assert effective_shopify_scopes(["read_orders", "read_customers"]) == {
        "read_orders",
        "read_customers",
    }


def test_shopify_webhook_hmac_verifies_exact_body(monkeypatch):
    import base64
    import hashlib
    import hmac

    from app.core.config import settings
    from app.integrations.providers.shopify.security import verify_webhook_hmac

    monkeypatch.setattr(settings, "shopify_client_secret", type("Secret", (), {"get_secret_value": lambda self: "test-secret"})())
    body = b'{"id":10,"title":"A"}'
    signature = base64.b64encode(hmac.new(b"test-secret", body, hashlib.sha256).digest()).decode()
    assert verify_webhook_hmac(body, signature)
    assert not verify_webhook_hmac(body + b" ", signature)

