# Phase 14 — AI observability and cost measurement

Tracking: [Production roadmap #10](https://github.com/Padam7890/supportpilot-ai/issues/10)

## Runtime implementation (slice 1)
The AI worker now emits one structured, privacy-safe generation metric after a successful grounded draft:
- execution and correlation IDs, execution kind, model identifier
- generation duration in milliseconds (monotonic clock)
- whether provisional widget streaming was enabled
- bounded provider-reported input/output/total token counts

Existing logs already include first Redis delta publish and first SSE delta delivery timestamps, and the browser marks its first delta and first DOM paint. These can be correlated by execution ID to identify which stage is slow.

The new record sets `cost_usd` to null because no verified model-specific price table has been integrated. **Do not interpret unknown cost as zero.**

## Remaining production work
- Persist metrics in a tenant-scoped reporting store with retention and access controls.
- Add accurate provider/model-specific pricing snapshots and account-level budgets.
- Build percentile latency dashboards and alerts.
- Measure actual provider first token, Redis-to-SSE and SSE-to-DOM latency end to end.
- Add coverage for errors, cancellations, retries and cost aggregation across all AI calls, not only grounded drafts.

## Required checks
```bash
cd backend
ruff check app/features/ai/application/generation_metrics.py app/services/ai_worker.py tests/test_generation_metrics.py
pytest -q tests/test_generation_metrics.py
```

**Status:** Runtime instrumentation committed; tests have not been executed.
