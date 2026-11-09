"""Shopify mutation dispatch safety tests."""
import pytest

from app.features.ai.application.shopify_dispatch_policy import authorize_shopify_dispatch


def decision(**overrides):
    payload = {
        "provider": "shopify",
        "action_type": "cancel",
        "approval_status": "approved",
        "execution_status": "running",
        "shopify_order_id": "gid://shopify/Order/123",
        "cancel_refund": False,
        "cancel_restock": False,
        "cancel_notify_customer": False,
    }
    payload.update(overrides)
    return authorize_shopify_dispatch(**payload)


def test_approved_plain_cancellation_allowed():
    assert decision().allowed


@pytest.mark.parametrize("action_type", ["refund", "edit", "capture", "unknown"])
def test_unsupported_mutations_denied(action_type):
    assert decision(action_type=action_type).reason == "shopify_action_not_supported"


@pytest.mark.parametrize("approval_status,execution_status", [
    ("pending", "running"), ("rejected", "running"), ("approved", "queued")
])
def test_unapproved_or_unclaimed_actions_denied(approval_status, execution_status):
    assert not decision(
        approval_status=approval_status, execution_status=execution_status
    ).allowed


@pytest.mark.parametrize("side_effect", [
    "cancel_refund", "cancel_restock", "cancel_notify_customer"
])
def test_high_impact_side_effects_denied(side_effect):
    assert decision(**{side_effect: True}).reason == "shopify_side_effects_require_explicit_review"


def test_wrong_provider_and_missing_order_denied():
    assert not decision(provider="mock").allowed
    assert not decision(shopify_order_id=None).allowed
