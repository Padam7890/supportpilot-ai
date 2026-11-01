# Product Recommendation System — Phase 7 Readiness Review

**Review date:** 2026-11-01  
**Scope:** Current SupportPilot catalog synchronization, Shopify adapter, recommendation API/worker, conversation recommendation state, merchant settings, analytics, and related frontend.

## Executive summary

The recommendation foundation is implemented and the backend is now migrated through `0029_recommendation_tenant_rls`. The Compose API is healthy, readiness returns HTTP 200, the runtime database-role/RLS checker passes, and the PostgreSQL-backed backend suite passes (203 tests). Frontend lint, type checking, unit tests, generated API-type drift checking, and production build were previously run successfully during this review cycle. Playwright could not start its local server because binding `127.0.0.1:3000` returned `EPERM`; end-to-end behavior therefore remains unverified.

This is **not a production-ready approval**. There is no full distributed tracing/metrics/alerting setup, the recommendation retrieval path has not been profiled against a representative large catalog, Shopify rate-limit handling does not honor `Retry-After`, and a live Shopify catalog synchronization/reconciliation was not performed as part of these checks.

## Implemented during this review

- LLM intent-extraction provider errors now fall back to the constrained deterministic parser rather than failing the whole recommendation execution. A regression test covers provider timeout fallback.
- Catalog sync status preserves the last successful synchronization timestamp when a later job fails, while still exposing the latest job/error state.
- Added migration `0029_recommendation_tenant_rls` to align recommendation-table policy names with the runtime RLS verifier.
- Expanded the runtime-role verifier to include recommendation settings and analytics tables.
- Expanded the Alembic version ledger column before migration `0028` writes its 38-character revision ID. This resolved the live migration failure caused by Alembic's default `VARCHAR(32)` ledger.
- Corrected integration-test fixtures to use unique Shopify store domains and fixed stale catalog/recommendation test setup discovered by the PostgreSQL-backed suite.
- Updated the backend environment example to document the Shopify `read_products` scope.

## Evidence and quality gates

| Check | Result | Evidence / limitation |
|---|---|---|
| Compose app migration | Passed | Live DB at `0029_recommendation_tenant_rls` (head). |
| API readiness | Passed | `GET /health/ready` returned HTTP 200; PostgreSQL and Redis connected. |
| Runtime DB role and forced RLS | Passed | `assert_runtime_db_role.py`: `supportpilot_app` on `supportpilot`, forced RLS verified on 31 tenant tables, migration ledger is read-only. |
| Backend integration suite | Passed | Isolated Compose PostgreSQL; 203 passed, 3 SQLAlchemy relationship warnings. |
| Backend Ruff | Passed | `ruff check app tests migrations scripts`. |
| OpenAPI export/drift | Passed | `scripts/export_openapi.py --check`. |
| Offline Alembic render | Passed | `alembic upgrade head --sql` rendered through revision 0029. This checks SQL generation, not a fresh-database execution. |
| Frontend lint | Passed | `npm run lint`. |
| Frontend type check | Passed | `npm run typecheck` (rerun after build to avoid transient `.next/types` deletion during concurrent build). |
| Frontend unit tests | Passed | 15 files, 29 tests. |
| Generated TypeScript API types | Passed | `npm run api:types:check`. |
| Frontend production build | Passed | `npm run build`. |
| Playwright E2E | Blocked | Web server could not bind `127.0.0.1:3000` (`listen EPERM`); no E2E cases ran. |
| Live Shopify API verification | Not run | No live provider sync/verification was performed during this readiness check. |

### Docker migration and restart

The requested migration/restart was performed. The initial migration attempt exposed the Alembic ledger width issue; the migration was fixed and applied. Services `api`, `worker`, and `frontend` were restarted; PostgreSQL and Redis remained running. At verification, API and frontend were healthy, worker was up, the migration head was 0029, and readiness returned 200.

## Reliability and security review

### Verified

- Catalog and recommendation queries are tenant-scoped; the PostgreSQL integration suite exercises cross-tenant product visibility and composite-FK rejection.
- Runtime role verification confirms forced RLS on 31 tenant tables, with a read-only migration ledger for the runtime DB role.
- Shopify webhook processing verifies HMAC signatures, associates incoming events with a connected tenant store, and records idempotency state.
- Catalog sync and AI execution work use bounded attempts; catalog retries use exponential backoff with jitter and terminal failed states.
- Shopify credentials remain server-side/encrypted; the frontend does not receive access tokens. Logs use safe identifiers and redact secrets.
- Recommendation intent output is validated and cannot construct SQL. Provider failure now has a deterministic fallback.
- Recommendation API output is structured and grounded in normalized catalog facts. No product action or purchase is executed by the model.

### Gaps and release risks

| Priority | Gap | Required follow-up |
|---|---|---|
| P0 | E2E registration/widget/recommendation workflows were not verified in this run. | Run Playwright in CI or a permitted isolated port and retain artifacts. |
| P1 | No production-grade trace/correlation propagation, metrics backend, dashboards, or actionable alert rules were evidenced. | Add request/job correlation IDs and operational metrics/alerts before external production use. Avoid logging raw customer content or credentials. |
| P1 | Candidate retrieval has a hard cap of 1,000 catalog candidates, and some filtering/ranking happens in Python after retrieval. No representative PostgreSQL query-plan or large-catalog benchmark was run. | Move applicable hard filters into indexed SQL, define behavior when candidate cap is reached, then benchmark with realistic tenant catalog sizes and `EXPLAIN ANALYZE`. |
| P1 | Shopify throttling handles retryable HTTP failures but does not honor Shopify's `Retry-After`/GraphQL throttle metadata. | Respect provider throttle signals and add bounded retry tests for 429/THROTTLED responses. |
| P1 | No live Shopify sync, webhook replay, deletion reconciliation, or reconnect verification was run. | Validate using a development store and record event/sync outcomes before enabling a staged merchant rollout. |
| P2 | No circuit breaker was found. Local-catalog recommendations can fall back when extraction fails, so a breaker may not be needed for every provider; verify with measured outage behavior. | Keep bounded timeouts/retries; add a breaker only if repeated downstream failures cause resource exhaustion. |
| P2 | Three SQLAlchemy overlapping-relationship warnings remain in `test_ai_integration.py` fixture setup. | Clarify relationship ownership/`overlaps` annotations and make warnings actionable rather than globally suppressing them. |
| P2 | Existing architecture documentation contains phase/acceptance statements that may not reflect current implementation. | Reconcile the Phase 1–6 architecture plan with actual test evidence and shipped features. |

## Performance observations

A local synthetic microbenchmark of the deterministic Python ranking function over 1,000 candidates, 10 runs, measured a median of **5.11 ms** (range **4.99–5.73 ms**). This excludes database retrieval, LLM intent extraction, serialization, network calls, queue delay, and end-to-end latency. It is only a ranking baseline, not a production SLO or evidence that the catalog query scales.

No trustworthy measurements were captured for intent extraction, candidate SQL retrieval, full worker latency, tokens/cost per recommendation, or catalog sizes representative of production. Establish those measurements before setting latency/cost SLOs.

## Environment and Shopify permissions

The backend requests `read_products` for Shopify catalog synchronization. The merchant must grant that scope to the app installation; if it is absent on an existing installation, update/re-authorize the app and verify actual granted scopes before syncing. Shopify documents that Admin GraphQL `Product` requires `read_products` and that access scopes are managed on the app installation:

- [Shopify Admin GraphQL `Product` access requirements](https://shopify.dev/docs/api/admin-graphql/latest/objects/product)
- [Shopify manage access scopes](https://shopify.dev/docs/apps/build/authentication-authorization/manage-access-scopes)

`backend/.env.example` documents the scope. Never put client secrets, access tokens, or encryption keys in frontend environment variables.

## Rollout and operational runbook

### Safe deployment order

1. Back up the database and confirm the migrator credentials are available.
2. Deploy the migration-capable backend image and run `alembic upgrade head` using the dedicated migrator role.
3. Verify migration head and run the runtime-role/RLS checker with the restricted application role.
4. Deploy/restart API and worker code; check `/health/ready`, worker process status, PostgreSQL, and Redis.
5. Enable recommendations for one internal tenant first. Verify catalog freshness, a recommendation result, error rate, and token/cost reporting.
6. Expand gradually while monitoring sync failures, queue age, recommendation latency, fallback rate, and provider throttling.

### Monitoring checklist

- API error rate and latency by route; queue depth/oldest job age; AI execution retries/failures.
- Catalog sync last-success age, failed job count, webhook signature failures, duplicate event counts, Shopify throttling.
- Recommendation no-result/fallback rate, retrieval latency, candidate cap hits, token/cost per execution.
- Database pool saturation, slow catalog queries, Redis connectivity, and migration head mismatch.
- Alerts must not include access tokens, customer email, raw chat text, or full sensitive provider payloads.

### Rollback

- Disable recommendations per tenant using the existing merchant settings before rolling back application code.
- Prefer forward-fix for schema rollback. Migration 0029 only renames recommendation RLS policies; if rollback is necessary, restore the previous policy names only after confirming no runtime checker or code depends on the new names.
- Migration 0028 downgrade intentionally refuses to discard stored recommendation analytics. Preserve/export events and settings before any destructive rollback.
- Keep encrypted Shopify credentials and catalog data intact; do not disconnect stores as a rollback shortcut.

## Acceptance decision

**Phase 7 review is complete as an audit and hardening pass, but production release remains blocked** until E2E flows run successfully, large-catalog retrieval is measured/optimized, Shopify live sync and throttle behavior are verified, and production observability/alerts are in place. Passing unit/integration checks do not substitute for those items.
