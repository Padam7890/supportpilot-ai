# Phase 10 — Production hardening and launch readiness

This is the final release phase, **not** a declaration that the product is production-ready.

## Release gates (must pass before launch)

| Gate | Evidence required | Status |
| --- | --- | --- |
| Backend and frontend CI | Passing tests, lint, typecheck, build, migrations | Unverified |
| Database | Reversible Alembic migrations, indexes, backup/restore rehearsal | Unverified |
| Tenant isolation | Cross-tenant API and RLS negative tests for all sensitive resources | Unverified |
| Authentication | OTP rate limiting, refresh/revoke, CSRF/CORS and session expiry tests | Unverified |
| Widget security | Allowed origins, tenant binding, replay protection, rate limits | Unverified |
| AI grounding | Phase 9 synthetic quality gate plus real-model evaluation | Partial |
| Tool safety | Commerce authorization, OTP order verification, refund approval and idempotency | Unverified |
| Streaming | SSE reconnect, fallback, cancellation, slow provider and proxy buffering | Unverified |
| Spend | Provider-attempt ledger for embeddings/router/retries and invoice reconciliation | Incomplete |
| Retention | Physical logs/telemetry lifecycle and deletion tests; preserve required business records | Incomplete |
| Observability | Alerts for latency, failure rates, queue depth, spend and integration errors | Incomplete |
| Channels | Shopify webhooks/OAuth/catalog/orders and WhatsApp webhook signature tests | Unverified |
| Deployment | Secrets, HTTPS, worker health, zero-downtime deploy and rollback rehearsal | Unverified |
| UX | Desktop/mobile inbox and widget E2E, keyboard and accessibility review | Unverified |

## Suggested execution order

1. Make CI mandatory and obtain a green run for the current main branch; fix failures before adding features.
2. Run security, tenant isolation and abuse-path regression suites.
3. Complete provider-call spend accounting and physically enforced telemetry retention.
4. Verify integrations, widget streaming and human handoff in staging.
5. Exercise deployment, backup restore and rollback; establish monitoring alerts.
6. Run a pilot with explicit release sign-off and a written rollback plan.

## Release decision

Do **not** mark any unverified gate passed. No customer launch until the critical security, data isolation, financial-action safety, rollback and CI gates pass. Keep this PR draft until independently verified.
