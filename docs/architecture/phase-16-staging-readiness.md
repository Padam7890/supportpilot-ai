# Phase 16 — Staging release readiness

Tracking: [Production hardening roadmap #10](https://github.com/Padam7890/supportpilot-ai/issues/10)

## Implemented
- Read-only staging preflight in `backend/scripts/staging_preflight.py`.
- HTTPS origin validation and bounded network timeout; no order/customer mutations.
- Requires `GET /health/ready` to return HTTP 200, JSON `status=ready`, `checks.database=connected`, and `checks.redis=connected`. The existing readiness endpoint also checks transactional SMTP configuration.
- Manual GitHub Actions workflow `staging-preflight.yml` with `staging` environment protection and a supplied HTTPS staging API origin.
- Tests for malformed origins, healthy/unhealthy dependencies and network errors.

## How to use
1. Deploy the latest migrations before the API and worker.
2. Configure a GitHub `staging` environment with required reviewers and restricted access.
3. Open Actions → Staging release preflight → Run workflow; enter the **HTTPS API origin**, such as `https://staging-api.example.com` (replace with the real origin).
4. A passing readiness check confirms basic dependencies only. It is **not** launch approval.

Local test:
```bash
cd backend
python scripts/staging_preflight.py --api-url https://your-real-staging-api.example
pytest -q tests/test_staging_preflight.py
ruff check scripts/staging_preflight.py tests/test_staging_preflight.py
```

## Required before public launch
- Run full CI, database migration and RLS checks.
- Execute two-tenant isolation, Shopify cancellation reconciliation, OTP and streaming browser tests.
- Measure RAG Recall@6, citation validity, and unsupported claims on staging.
- Verify backup/restore, secrets rotation, alerts, worker recovery and rollback rehearsal.
- Conduct a limited pilot with explicit merchant approval and documented incident handling.

**Status:** Real staging workflow and probe committed; no staging URL was supplied and no live deployment check has been executed.
