# Phase 8 — AI observability and cost accounting

## Implemented in this increment

- Provider usage aliases are normalized into input, output and total token counts without double-counting.
- Missing provider usage stays unknown rather than being inferred from response text.
- Generation logs include bounded duration, execution/correlation identifiers, model name and token counts, never prompts or responses.
- When both input and output prices are explicitly configured, estimated generation cost is calculated using Decimal with 8 decimal places.
- Actual billing cost remains null; configured price estimates are **not invoices**.
- Tests cover token aliases, missing counters, negative/nonfinite prices and deterministic cost arithmetic.

## Existing product capabilities

The application already exposes a tenant-scoped `GET /analytics/ai-usage` endpoint, per-bot usage, daily usage, failures, latency and configurable token prices. Extend and validate these instead of introducing a duplicate analytics API.

## Remaining release gates

1. Confirm configured prices correspond to the actual selected provider/model and pricing date. Do not treat one global price pair as valid across different models.
2. Audit whether all model calls, including router, embeddings and retries, are represented in tenant cost accounting. Current generation estimates are not total AI spend.
3. Ensure missing token counters do not appear as zero in dashboard totals or cost estimates.
4. Add request/worker tracing and latency histograms with bounded label cardinality; no PII, prompts, raw responses, or secrets in metrics.
5. Add per-tenant budgets, alerts, throttling and retention policy after cost accounting is verified.
6. Execute backend pytest, frontend checks and full-stack browser workflows; investigate any failures before merging.

No tests have been executed through the GitHub connector for this PR.
