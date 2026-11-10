"""Verified-order evidence must not leak raw Shopify payload fields."""

import pytest

from app.features.ai.application.conversation_verified_order_evidence import (
    build_verified_order_evidence,
)


def test_unverified_customer_cannot_create_order_evidence() -> None:
    with pytest.raises(PermissionError):
        build_verified_order_evidence(
            {"fulfillment_status": "fulfilled"}, identity_verified=False,
        )


def test_only_approved_scalar_fields_reach_model_evidence() -> None:
    result = build_verified_order_evidence(
        {
            "order_name": "#1234",
            "fulfillment_status": "fulfilled",
            "email": "customer@example.com",
            "shipping_address": {"address1": "private street"},
            "access_token": "secret",
        },
        identity_verified=True,
    )
    combined = " ".join(item["content"] for item in result.evidence.context)
    assert "fulfilled" in combined
    assert "#1234" in combined
    assert "customer@example.com" not in combined
    assert "private street" not in combined
    assert "secret" not in combined


def test_empty_and_nested_unrecognized_payload_fails_closed() -> None:
    with pytest.raises(ValueError):
        build_verified_order_evidence(
            {"order": {"fulfillment_status": "fulfilled"}},
            identity_verified=True,
        )
