# Phase 9 — baseline verification

Tracking: [Production hardening roadmap #10](https://github.com/Padam7890/supportpilot-ai/issues/10)

## Goal
Create reproducible evidence about the current merged `main` branch before changing conversation architecture. No test pass rate or production readiness is assumed.

## How to run
Install the normal backend and frontend dependencies, start PostgreSQL and Redis with the repository's documented development configuration, apply test migrations, then run:

```bash
bash backend/scripts/phase9_baseline.sh
```

The script continues after individual failures and creates `phase-9-baseline-results/summary.tsv` plus separate logs. Use a path outside the repo if desired:

```bash
bash backend/scripts/phase9_baseline.sh /tmp/supportpilot-phase9-baseline
```

## Required additional checks (not run by the script)
- `docker compose -f compose.yaml config --quiet` with configured environment
- `cd backend && alembic current && alembic heads` against the intended test DB
- `cd backend && python scripts/assert_runtime_db_role.py` with provisioned roles
- `cd frontend && npm run build` in a properly configured environment
- CI status on the PR, and browser-based widget/Shopify staging tests

## Reporting template
| Check | Outcome | Evidence / failure | Owner | Follow-up |
| --- | --- | --- | --- | --- |
| Backend lint | Not run | — | — | — |
| OpenAPI contract | Not run | — | — | — |
| Backend tests | Not run | — | — | — |
| Frontend widget syntax | Not run | — | — | — |
| Frontend lint | Not run | — | — | — |
| Frontend types | Not run | — | — | — |
| Frontend tests | Not run | — | — | — |
| Migrations and RLS | Not run | — | — | — |
| Shopify browser E2E | Not run | — | — | — |

## Exit criteria
1. All baseline commands executed in CI or staging with retained logs.
2. Failures triaged into code defects, missing infrastructure, and flaky tests.
3. Critical security and data-isolation failures fixed before moving to Phase 10.
4. Latency baseline captured for at least the knowledge, order and casual-chat routes.

**Status:** In progress. The runner and documentation are committed, but no test or staging run is claimed.
