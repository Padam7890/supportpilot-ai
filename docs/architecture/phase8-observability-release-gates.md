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


## Model pricing configuration

Set `AI_MODEL_PRICES` to a JSON object mapping the **exact provider-reported model identifier** to USD prices per million tokens. Example (illustrative rates only, not verified vendor pricing):

```dotenv
AI_MODEL_PRICES={"example-model-a":{"input":0.10,"output":0.40},"example-model-b":{"input":0.20,"output":0.80}}
AI_METRICS_RETENTION_DAYS=90
```

The legacy `AI_INPUT_COST_PER_MILLION` and `AI_OUTPUT_COST_PER_MILLION` remain fallback rates for `AI_MODEL` only. The tenant analytics endpoint computes cost per recorded execution using its model identifier and token counters. If any execution in the selected window lacks known pricing or complete usage, the aggregate estimate is null rather than a misleading partial total. Per-bot estimates follow the same rule.

The 90-day retention window is enforced at the AI usage analytics endpoint. This **does not physically purge** application logs, AI execution records, customer conversations, backups, or external monitoring data. Configure actual log storage retention in your deployment separately. Historical business records are deliberately not deleted by metrics retention.

The dashboard summarizes AI execution failures and usage. Full spend accounting is **not** complete until embeddings, intent routing, retries, failed billable provider calls, and provider billing reconciliation are captured independently. Model pricing requires a verified price source and effective date. No successful CI run has been verified for these changes.
