"""Canonical identity helpers shared by commerce action entry points."""

import hashlib
import json

from app.schemas.commerce_action import CommerceActionCreate


def commerce_action_fingerprint(payload: CommerceActionCreate) -> str:
    canonical = json.dumps(
        {
            "ticket_id": str(payload.ticket_id),
            "order_number": payload.order_number.strip().lstrip("#").casefold(),
            "action_type": payload.action_type,
            "provider": payload.provider,
            "refund_amount": str(payload.refund_amount)
            if payload.refund_amount is not None
            else None,
            "cancel_refund": payload.cancel_refund,
            "cancel_restock": payload.cancel_restock,
            "cancel_notify_customer": payload.cancel_notify_customer,
            "cancellation_reason": payload.cancellation_reason,
            "reason": payload.reason.strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def commerce_idempotency_hash(key: str) -> str:
    return hashlib.sha256(key.strip().encode()).hexdigest()
