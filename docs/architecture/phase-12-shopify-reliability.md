# Phase 12 — Shopify workflow reliability

Tracking: [Production hardening roadmap #10](https://github.com/Padam7890/supportpilot-ai/issues/10)

## Implemented in this slice
- Fix unsafe lease-recovery behavior: previously a Shopify cancellation with a timed-out `running` lease could be dispatched a second time.
- Expired Shopify running leases now transition to `failed` with `shopify_outcome_unknown_manual_review` and an audit event. They are not automatically retried.
- Keep first-time queued Shopify actions dispatchable and allow the existing mock adapter's bounded retry behavior.
- Add pure decision tests for expired leases, exhausted attempts, active leases, and invalid providers.

## Important operational behavior
`failed` + `shopify_outcome_unknown_manual_review` does **not** mean Shopify failed. It means the remote outcome is uncertain. An operator must reconcile Shopify order state and audit history before any new mutation. Do not blindly requeue the action.

## Remaining production gaps
- Tests and real Shopify staging failure injection have not been executed.
- Existing worker processes could still be active when a lease expires. Preventing concurrent remote mutation requires provider-side idempotency or a stronger execution fencing strategy.
- Build an explicit reconciliation workflow and merchant UI for unknown outcomes.
- Test OTP expiry, duplicate cancellation requests, webhook delays, API outages, permission changes and order-state races.
- Verify approval and order-state checks before the final provider mutation.

## Required checks
```bash
cd backend
ruff check app/services/commerce_action_recovery.py app/services/commerce_action_worker.py tests/test_commerce_action_recovery.py
pytest -q tests/test_commerce_action_recovery.py tests/test_commerce_actions_unit.py tests/test_commerce_actions_integration.py
```

This change prioritizes avoiding duplicate customer-impacting actions over automatic retries.
