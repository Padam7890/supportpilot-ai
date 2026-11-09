# Phase 6 — Shopify mutation safety

## Enforcement points

1. Staff requests: only Shopify cancellations are supported. Refund, restock and customer notification side effects are rejected at request creation.
2. Staff approval: owner/admin approval is required and the dispatch policy is checked before queueing.
3. Worker dispatch: the same policy is rechecked after the job is claimed, before any provider mutation. The order must be re-fetched using the ticket customer's email and exact order number; the returned Shopify GID must match the approved action.
4. Provider result: a completed async Shopify job is **not** a successful cancellation unless its status is explicitly SUCCEEDED. Mismatched order IDs fail.
5. Retry: ambiguous Shopify mutations are not automatically retried. A failed/unknown outcome requires manual reconciliation.
6. Audit: existing request, approval, execution and failure events remain recorded.

## Restrictions

The current Phase 6 policy intentionally blocks Shopify cancellation refund, restock and notification flags even when staff set them. These side effects need a dedicated explicit approval and preview contract before re-enabling them. Shopify refunds and order edits are not implemented.

## Verification required before production

- Run: `cd backend && pytest -q tests/test_shopify_dispatch_policy.py tests/test_shopify_cancellation_result_safety.py tests/test_widget_integration.py`
- Run backend Ruff and the full backend test suite with a real isolated PostgreSQL test database.
- Verify an approved cancellation on a disposable Shopify development-store order, including re-verification and the resulting audit record.
- Exercise rejected, expired, duplicate and mismatched-order actions, plus Shopify job states PENDING, FAILED, and SUCCEEDED.
- Review frontend toggles for disabled side effects so the UI does not promise unavailable actions.

No live Shopify mutation or local test execution was performed through the GitHub connector.
