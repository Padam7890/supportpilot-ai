# Phase 9 — AI evaluation and quality assurance

## First increment

Expand the existing tenant-scoped teammate feedback API so completed `widget_reply`, `playground`, and `reply_draft` AI executions can be evaluated. Reuse the existing evaluation table and permission checks. No customer message text is added to analytics logs.

## Quality gates to implement

1. Build a versioned, tenant-isolated offline evaluation set covering grounded knowledge answers, missing knowledge, ambiguous questions, order verification, refunds, handoff, multi-turn context, and prompt injection.
2. Run deterministic policy checks for tenant isolation, tool authorization, unsupported numeric claims, and citation access before scoring any LLM output.
3. Capture outcome labels for answer relevance, grounding, tool correctness, refusal/handoff and latency, with trace IDs but without raw private customer content in telemetry.
4. Compare baseline and candidate models/prompts on identical fixtures; report per-category pass rates and regressions, not only one aggregate score.
5. Add a deployment gate for critical failures; no model or prompt change should be promoted if it violates privacy or tool-authorization constraints.
6. Run backend/frontend checks, E2E tests and a staged real-provider evaluation before declaring production readiness.

The Phase 8 merge is independent of the unresolved full-spend reconciliation and physical log-retention work, which remain open technical debt.
