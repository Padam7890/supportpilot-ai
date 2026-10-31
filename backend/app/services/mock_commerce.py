"""Deterministic commerce simulator; never calls Shopify write APIs."""

from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5


class MockCommerceService:
    async def execute(
        self,
        *,
        idempotency_key_hash: str,
        action_type: str,
        order_number: str,
        refund_amount: Decimal | None,
        currency: str,
    ) -> dict[str, str]:
        """Return a stable simulated outcome for retries of the same action."""
        operation_id = uuid5(NAMESPACE_URL, f"supportpilot-commerce:{idempotency_key_hash}")
        result = {
            "provider": "mock_commerce",
            "execution": "simulated",
            "operation_id": str(operation_id),
            "action_type": action_type,
            "order_number": order_number,
        }
        if refund_amount is not None:
            result["refund_amount"] = format(refund_amount, ".2f")
            result["currency"] = currency
        return result
