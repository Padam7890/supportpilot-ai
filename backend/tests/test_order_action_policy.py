"""Security-focused tests for Shopify order action policy."""
import pytest

from app.features.ai.application.order_action_policy import authorize_order_action


@pytest.mark.parametrize("action", ["track", "cancel", "refund", "return"])
def test_unverified_customer_cannot_act(action: str) -> None:
    result = authorize_order_action(
        action, verified=False,
        verification_tenant_matches=True,
        verification_conversation_matches=True,
    )
    assert result.decision == "request_verification"


@pytest.mark.parametrize("tenant_ok,conversation_ok", [(False, True), (True, False), (False, False)])
def test_cross_tenant_or_conversation_verification_is_rejected(
    tenant_ok: bool, conversation_ok: bool
) -> None:
    result = authorize_order_action(
        "track", verified=True,
        verification_tenant_matches=tenant_ok,
        verification_conversation_matches=conversation_ok,
    )
    assert result.decision == "request_verification"


def test_verified_tracking_can_be_read() -> None:
    result = authorize_order_action(
        "track", verified=True,
        verification_tenant_matches=True,
        verification_conversation_matches=True,
    )
    assert result.decision == "allow_read"


@pytest.mark.parametrize("action", ["cancel", "refund", "return"])
def test_verified_mutations_still_require_merchant_review(action: str) -> None:
    result = authorize_order_action(
        action, verified=True,
        verification_tenant_matches=True,
        verification_conversation_matches=True,
    )
    assert result.decision == "request_human_review"
