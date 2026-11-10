"""Minimize server-verified Shopify order context before model composition.

This module does NOT verify identity or fetch Shopify data. Callers must supply
context obtained from the existing authorized order-verification workflow.
Never pass raw decrypted payloads, contact details, addresses or tokens to an LLM.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.features.ai.application.conversation_response_evidence import ResponseEvidence

_ALLOWED_SCALARS = frozenset({
    "order_name", "order_number", "financial_status", "fulfillment_status",
    "display_fulfillment_status", "cancelled_at", "processed_at",
    "currency", "total_price", "tracking_company", "tracking_number",
    "tracking_url",
})


@dataclass(frozen=True)
class VerifiedOrderEvidence:
    evidence: ResponseEvidence
    accepted_fields: tuple[str, ...]


def build_verified_order_evidence(
    context: Mapping[str, object] | None,
    *,
    identity_verified: bool,
) -> VerifiedOrderEvidence:
    """Fail closed; caller owns verification and execution-scoped authorization."""
    if not identity_verified or not isinstance(context, Mapping):
        raise PermissionError("Verified customer identity is required")
    facts: list[str] = []
    accepted: list[str] = []
    for field in sorted(_ALLOWED_SCALARS):
        value = context.get(field)
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            continue
        value_text = str(value).strip()
        if not value_text or len(value_text) > 160:
            continue
        # Avoid multiline prompt injection or arbitrary provider payloads.
        if any(char in value_text for char in "\r\n<>"):
            continue
        facts.append(f"{field}: {value_text}")
        accepted.append(field)
    if not facts:
        raise ValueError("No approved verified order fields available")
    return VerifiedOrderEvidence(
        evidence=ResponseEvidence(
            context=[{"source": "verified_shopify_order", "content": fact} for fact in facts],
            source_ids=[],
            answerable=True,
            unavailable=False,
        ),
        accepted_fields=tuple(accepted),
    )
