"""Fail-closed Shopify mutation dispatch policy.

Only a previously approved cancellation can reach Shopify's mutation API.
Refunds, edits and other actions require separately reviewed implementations.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ShopifyDispatchDecision:
    allowed: bool
    reason: str


def authorize_shopify_dispatch(
    *,
    provider: str,
    action_type: str,
    approval_status: str,
    execution_status: str,
    shopify_order_id: str | None,
    cancel_refund: bool,
    cancel_restock: bool,
    cancel_notify_customer: bool,
) -> ShopifyDispatchDecision:
    if provider != "shopify":
        return ShopifyDispatchDecision(False, "invalid_provider")
    if approval_status != "approved" or execution_status != "running":
        return ShopifyDispatchDecision(False, "action_not_approved_or_claimed")
    if action_type != "cancel":
        return ShopifyDispatchDecision(False, "shopify_action_not_supported")
    if not shopify_order_id or not shopify_order_id.startswith("gid://shopify/Order/"):
        return ShopifyDispatchDecision(False, "invalid_shopify_order_id")
    # High-impact side effects require a separate, explicit approval contract.
    if cancel_refund or cancel_restock or cancel_notify_customer:
        return ShopifyDispatchDecision(False, "shopify_side_effects_require_explicit_review")
    return ShopifyDispatchDecision(True, "approved_cancellation")
