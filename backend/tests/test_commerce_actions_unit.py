from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.services.commerce_action_identity import (
    commerce_action_fingerprint as fingerprint,
    commerce_idempotency_hash as idempotency_hash,
)
from app.schemas.commerce_action import CommerceActionCreate
from app.services.mock_commerce import MockCommerceService


def test_commerce_action_request_requires_amount_only_for_refunds():
    shared = {"ticket_id": "00000000-0000-0000-0000-000000000001", "order_number": "#1001", "reason": "Item arrived damaged"}
    with pytest.raises(ValidationError):
        CommerceActionCreate(**shared, action_type="refund")
    with pytest.raises(ValidationError):
        CommerceActionCreate(**shared, action_type="cancel", refund_amount="10.00")

    refund = CommerceActionCreate(**shared, action_type="refund", refund_amount="10.00")
    cancel = CommerceActionCreate(**shared, action_type="cancel")
    assert refund.refund_amount == Decimal("10.00")
    assert cancel.refund_amount is None


def test_idempotency_hash_and_request_fingerprint_are_stable_and_non_reversible_values():
    first = CommerceActionCreate(
        ticket_id="00000000-0000-0000-0000-000000000001",
        order_number="#1001",
        action_type="refund",
        refund_amount="10.00",
        reason="Item arrived damaged",
    )
    equivalent = CommerceActionCreate(
        ticket_id="00000000-0000-0000-0000-000000000001",
        order_number="1001",
        action_type="refund",
        refund_amount="10.00",
        reason="Item arrived damaged",
    )
    assert fingerprint(first) == fingerprint(equivalent)
    assert idempotency_hash("client-generated-key-0001") == idempotency_hash("client-generated-key-0001")
    assert idempotency_hash("client-generated-key-0001") != "client-generated-key-0001"


@pytest.mark.anyio
async def test_mock_commerce_execution_is_deterministic_for_idempotent_retries():
    service = MockCommerceService()
    args = {
        "idempotency_key_hash": "a" * 64,
        "action_type": "refund",
        "order_number": "#1001",
        "refund_amount": Decimal("12.50"),
        "currency": "USD",
    }
    first = await service.execute(**args)
    second = await service.execute(**args)
    assert first == second
    assert first["provider"] == "mock_commerce"
    assert first["execution"] == "simulated"
    assert first["refund_amount"] == "12.50"
