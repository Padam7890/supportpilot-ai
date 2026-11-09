"""Pure authorization gates for customer-facing Shopify workflow actions.

These gates do not grant authorization. Callers must use server-validated
verification records, scoped to the current tenant and conversation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Action = Literal["track", "cancel", "refund", "return"]
Decision = Literal["allow_read", "request_verification", "request_human_review"]


@dataclass(frozen=True)
class OrderActionDecision:
    decision: Decision
    reason: str


def authorize_order_action(
    action: Action,
    *,
    verified: bool,
    verification_tenant_matches: bool,
    verification_conversation_matches: bool,
) -> OrderActionDecision:
    """Fail closed unless server-side verification matches this request."""
    if not (
        verified
        and verification_tenant_matches
        and verification_conversation_matches
    ):
        return OrderActionDecision("request_verification", "verification_required")
    if action == "track":
        return OrderActionDecision("allow_read", "verified_order_read")
    return OrderActionDecision("request_human_review", "merchant_approval_required")
