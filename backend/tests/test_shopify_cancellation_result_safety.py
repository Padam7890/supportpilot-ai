"""Shopify cancellation provider-result safety regression tests."""
import pytest

from app.integrations.providers.shopify import actions
from app.integrations.providers.shopify.actions import ShopifyOrderActionError


@pytest.mark.asyncio
async def test_completed_job_without_success_is_not_reported_as_cancelled(monkeypatch):
    async def fake_graphql(*args, **kwargs):
        return {"orderCancel": {
            "orderCancelUserErrors": [],
            "jobResult": {
                "id": "gid://shopify/OrderCancelJobResult/1",
                "done": True,
                "status": "PENDING",
                "errors": [],
                "order": {"id": "gid://shopify/Order/123"},
            },
        }}
    monkeypatch.setattr(actions, "graphql", fake_graphql)
    with pytest.raises(ShopifyOrderActionError) as exc:
        await actions.cancel_shopify_order(
            shop_domain="example.myshopify.com",
            access_token="test",
            order_id="gid://shopify/Order/123",
            notify_customer=False,
            refund=False,
            restock=False,
            reason="CUSTOMER",
            staff_note="Approved by merchant",
        )
    assert exc.value.code == "shopify_cancel_outcome_unknown_manual_review"


@pytest.mark.asyncio
async def test_successful_job_with_wrong_order_is_rejected(monkeypatch):
    async def fake_graphql(*args, **kwargs):
        return {"orderCancel": {
            "orderCancelUserErrors": [],
            "jobResult": {
                "id": "gid://shopify/OrderCancelJobResult/1",
                "done": True,
                "status": "SUCCEEDED",
                "errors": [],
                "order": {"id": "gid://shopify/Order/999"},
            },
        }}
    monkeypatch.setattr(actions, "graphql", fake_graphql)
    with pytest.raises(ShopifyOrderActionError) as exc:
        await actions.cancel_shopify_order(
            shop_domain="example.myshopify.com",
            access_token="test",
            order_id="gid://shopify/Order/123",
            notify_customer=False,
            refund=False,
            restock=False,
            reason="CUSTOMER",
            staff_note="Approved by merchant",
        )
    assert exc.value.code == "shopify_cancel_order_mismatch"
