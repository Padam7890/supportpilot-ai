# Release readiness report (evidence-based)

Generated as part of the RAG hardening pass. **This is not a launch approval.**

## Migrations

| Revision | Applied (dev) | Notes |
|----------|---------------|-------|
| 0070–0073 | Run `alembic current` in your env | 0073 adds `content_hash`; orphans removed |

## Tests executed (API container)

| Suite | Result |
|-------|--------|
| Full `pytest` | Run after pull: see CI or `docker compose exec api pytest -q` |

_Last verified run in engineering pass: **346+ passed** (64 skipped) after fencing + corpus 100 — re-run locally to confirm._

## RAG evaluation

| Metric | Result |
|--------|--------|
| Corpus size | **100** cases (`tests/rag_eval/corpus.json`) |
| Intent-term overlap | From `python scripts/rag_eval_report.py` |
| Recall@6 on fixture DB | **NOT VERIFIED** |
| Citation validity % | **NOT VERIFIED** |
| Unsupported-claim rate | **NOT VERIFIED** |

## Proposed launch gates (not achieved claims)

| Gate | Status |
|------|--------|
| 95% Recall@6 | **NOT VERIFIED** |
| 98% citation validity | **NOT VERIFIED** |
| Zero cross-tenant leakage | Partial — existing integration tests; re-run in staging |
| p95 retrieval < 500 ms | **NOT VERIFIED** on staging workload |

## Rollback

1. `alembic downgrade 0072` only after reviewing 0073 data loss (embedding hash column).
2. Redeploy previous API/worker images.
3. Re-enqueue embedding jobs if vectors were removed by 0073 backfill.

## Remaining risks

- Optional reranking disabled by default.
- HNSW conditional on uniform 1536-d vectors.
- End-to-end widget conversations require manual staging validation.
