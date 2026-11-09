"""Conservative retry policy for approved commerce mutations.

A Shopify cancellation can succeed remotely even when the worker loses its
response. Never treat lease expiration as proof that the mutation did not occur.
"""
from __future__ import annotations

from typing import Literal

LeaseDecision = Literal["dispatch", "manual_reconciliation", "retry_limit"]


def decide_lease_recovery(
    *, provider: str, status: str, lease_expired: bool,
    attempts: int, max_attempts: int
) -> LeaseDecision:
    if status not in {"queued", "running"}:
        raise ValueError("Action is not claimable")
    if provider not in {"shopify", "mock"}:
        raise ValueError("Unsupported provider")
    if attempts < 0 or max_attempts < 1:
        raise ValueError("Invalid attempt count")
    if status == "running" and not lease_expired:
        raise ValueError("Active lease cannot be reclaimed")
    if provider == "shopify" and status == "running":
        return "manual_reconciliation"
    if attempts >= max_attempts:
        return "retry_limit"
    return "dispatch"
