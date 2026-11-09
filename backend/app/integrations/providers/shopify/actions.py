"""Narrow Shopify order-action service. No LLM-facing write operations."""

import asyncio
from typing import Any

from app.integrations.providers.shopify.client import ShopifyAPIError, graphql

__all__ = [
    "CANCEL_RESULT_QUERY",
    "ORDER_CANCEL_MUTATION",
    "ShopifyOrderActionError",
    "cancel_shopify_order",
    "check_cancellation_eligibility",
    "check_cancellation_scope",
]

ORDER_CANCEL_MUTATION = """
mutation SupportPilotOrderCancel(
  $orderId: ID!,
  $notifyCustomer: Boolean!,
  $refundMethod: OrderCancelRefundMethodInput!,
  $restock: Boolean!,
  $reason: OrderCancelReason!,
  $staffNote: String
) {
  orderCancel(
    orderId: $orderId,
    notifyCustomer: $notifyCustomer,
    refundMethod: $refundMethod,
    restock: $restock,
    reason: $reason,
    staffNote: $staffNote
  ) {
    jobResult {
      id
      done
      status
      errors { field message code }
      order { id name cancelledAt }
    }
    orderCancelUserErrors { field message code }
  }
}
"""

CANCEL_RESULT_QUERY = """
query SupportPilotOrderCancelResult($id: ID!) {
  node(id: $id) {
    ... on OrderCancelJobResult {
      id
      done
      status
      errors { field message code }
      order { id name cancelledAt }
    }
  }
}
"""


class ShopifyOrderActionError(Exception):
    """An allowlisted failure code safe to persist and show in the workspace."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def check_cancellation_scope(granted_scopes: list[str] | set[str] | tuple[str, ...]) -> None:
    if "write_orders" not in set(granted_scopes):
        raise ShopifyOrderActionError("shopify_cancel_permission_denied")


def check_cancellation_eligibility(order: dict[str, Any]) -> None:
    if order.get("cancelledAt"):
        raise ShopifyOrderActionError("shopify_order_already_cancelled")
    if order.get("closed"):
        raise ShopifyOrderActionError("shopify_order_not_cancelable")
    if order.get("returnStatus") in {"RETURN_REQUESTED", "IN_PROGRESS"}:
        raise ShopifyOrderActionError("shopify_order_has_active_return")


def _errors_have_values(errors: Any) -> bool:
    return isinstance(errors, list) and bool(errors)


def _error_codes(errors: Any) -> list[str]:
    codes: set[str] = set()
    if not isinstance(errors, list):
        return []
    for entry in errors:
        if not isinstance(entry, dict):
            continue
        code = entry.get("code")
        if isinstance(code, str):
            codes.add(code)
    return sorted(codes)


def _safe_job_result(value: Any, *, expected_order_id: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ShopifyOrderActionError("shopify_cancel_invalid_response")
    errors = value.get("errors")
    if _errors_have_values(errors):
        codes = _error_codes(errors)
        raise ShopifyOrderActionError(codes[0] if codes else "shopify_cancel_failed")
    order = value.get("order")
    if isinstance(order, dict) and order.get("id") != expected_order_id:
        raise ShopifyOrderActionError("shopify_cancel_order_mismatch")
    return {
        "provider": "shopify",
        "operation": "order_cancel",
        "status": value.get("status"),
        "shopify_job_id": value.get("id"),
        "order_id": order.get("id") if isinstance(order, dict) else expected_order_id,
        "order_number": order.get("name") if isinstance(order, dict) else None,
        "cancelled_at": order.get("cancelledAt") if isinstance(order, dict) else None,
    }


async def cancel_shopify_order(
    *,
    shop_domain: str,
    access_token: str,
    order_id: str,
    notify_customer: bool,
    refund: bool,
    restock: bool,
    reason: str,
    staff_note: str,
    poll_attempts: int = 20,
    poll_interval_seconds: float = 1.0,
) -> dict[str, Any]:
    """Cancel after a separate human approval; refund/notify choices are explicit."""
    try:
        data = await graphql(
            shop_domain,
            access_token,
            ORDER_CANCEL_MUTATION,
            {
                "orderId": order_id,
                "notifyCustomer": notify_customer,
                "refundMethod": {"originalPaymentMethodsRefund": refund},
                "restock": restock,
                "reason": reason,
                "staffNote": staff_note[:255],
            },
        )
    except ShopifyAPIError as exc:
        if exc.status_code == 403:
            raise ShopifyOrderActionError("shopify_cancel_permission_denied") from exc
        raise ShopifyOrderActionError("shopify_cancel_provider_error") from exc

    payload = data.get("orderCancel")
    if not isinstance(payload, dict):
        raise ShopifyOrderActionError("shopify_cancel_invalid_response")
    if _errors_have_values(payload.get("orderCancelUserErrors")):
        error_codes = _error_codes(payload["orderCancelUserErrors"])
        raise ShopifyOrderActionError(error_codes[0] if error_codes else "shopify_cancel_rejected")
    job_result = payload.get("jobResult")
    if not isinstance(job_result, dict):
        raise ShopifyOrderActionError("shopify_cancel_invalid_response")

    for attempt in range(max(1, poll_attempts)):
        status = job_result.get("status")
        if job_result.get("done") is True or status in {"SUCCEEDED", "FAILED"}:
            result = _safe_job_result(job_result, expected_order_id=order_id)
            if status == "FAILED":
                raise ShopifyOrderActionError("shopify_cancel_failed")
            # A completed job is not necessarily a successful cancellation.
            if status != "SUCCEEDED":
                raise ShopifyOrderActionError("shopify_cancel_outcome_unknown_manual_review")
            return result
        job_id = job_result.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise ShopifyOrderActionError("shopify_cancel_invalid_response")
        if attempt + 1 >= max(1, poll_attempts):
            break
        await asyncio.sleep(poll_interval_seconds)
        try:
            polled = await graphql(
                shop_domain,
                access_token,
                CANCEL_RESULT_QUERY,
                {"id": job_id},
            )
        except ShopifyAPIError as exc:
            if exc.status_code == 403:
                raise ShopifyOrderActionError("shopify_cancel_permission_denied") from exc
            raise ShopifyOrderActionError("shopify_cancel_provider_error") from exc
        job_result = polled.get("node")
        if job_result is None:
            raise ShopifyOrderActionError("shopify_cancel_result_unavailable")

    raise ShopifyOrderActionError("shopify_cancel_result_pending")
