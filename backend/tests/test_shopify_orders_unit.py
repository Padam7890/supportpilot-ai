import pytest


@pytest.mark.anyio
async def test_authorized_order_lookup_requires_exact_number_and_customer_email(monkeypatch):
    from app.services import shopify_orders

    calls = []

    async def fake_fetch_orders(shop_domain, access_token, *, search_query, limit, cursor):
        calls.append((shop_domain, access_token, search_query, limit, cursor))
        return {
            "nodes": [
                {"name": "#1001", "customer": {"email": "other@example.com"}},
                {"name": "#1002", "customer": {"email": "morgan@example.com"}},
                {"name": "#1001", "customer": {"email": "morgan@example.com"}},
            ],
            "page_info": {"hasNextPage": False, "endCursor": None},
        }

    monkeypatch.setattr(shopify_orders, "fetch_orders", fake_fetch_orders)
    result = await shopify_orders.lookup_authorized_order(
        shop_domain="demo-store.myshopify.com",
        access_token="private-token",
        order_number="1001",
        customer_email="Morgan@Example.com",
    )

    assert result == {"name": "#1001", "customer": {"email": "morgan@example.com"}}
    assert calls == [(
        "demo-store.myshopify.com",
        "private-token",
        'name:"#1001" AND email:"morgan@example.com"',
        5,
        None,
    )]


@pytest.mark.anyio
async def test_authorized_order_lookup_returns_none_for_non_matching_identity(monkeypatch):
    from app.services import shopify_orders

    async def fake_fetch_orders(*_args, **_kwargs):
        return {
            "nodes": [{"name": "#1001", "customer": {"email": "someone-else@example.com"}}],
            "page_info": {"hasNextPage": False, "endCursor": None},
        }

    monkeypatch.setattr(shopify_orders, "fetch_orders", fake_fetch_orders)
    result = await shopify_orders.lookup_authorized_order(
        shop_domain="demo-store.myshopify.com",
        access_token="private-token",
        order_number="#1001",
        customer_email="morgan@example.com",
    )

    assert result is None
