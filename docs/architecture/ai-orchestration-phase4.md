# AI Orchestration Boundaries

For the current generation pipeline and rollout, see [LLM-first conversation engine](llm-first-conversation-engine.md). This document records the earlier Phase 4 split of AI execution, grounded support replies, RAG context, and recommendations. It is an incremental modular-monolith refactor: database models, migrations, API response schemas, and persisted LangGraph checkpoints remain unchanged.

## Package boundaries

```text
API / PostgreSQL worker
        |
        v
features/ai/application   execution context, widget gating and persistence, verified order context
        |
        +---- domain/      shopping state transitions, deterministic ranking, safe failure and reply policies
        +---- tools/       allowlisted Pydantic recommendation tool input/output schemas
        +---- workflows/   focused grounded-support LangGraph
        +---- infrastructure/  bounded LLM gateway and tenant-scoped Postgres checkpoint lifecycle
```

- `infrastructure/llm_gateway.py` owns transport, URL validation, request timeout, per-call output limits, aggregate execution token budgets, usage normalization, and redacted structured telemetry. It never logs prompts, outputs, credentials, or provider response bodies.
- `infrastructure/checkpoints.py` preserves the existing schema, table setup, tenant RLS policy, advisory lock, and checkpoint DSN behavior.
- `workflows/grounded_reply.py` owns the existing `prepare_prompt -> generate_draft` graph. Its thread ID remains `<organization UUID>:<AIExecution UUID>` and recursion limit remains five, so existing checkpoint rows remain addressable.
- `application/context.py` loads the tenant-scoped execution, bounded transcript, verified order context, and matching ready knowledge excerpts. Internal notes and customer-provided identity claims are excluded as before.
- `application/widget_replies.py` owns the conversation-row-locked final check and write. Human takeover, a newer customer message, or a teammate reply prevents the AI response from being persisted/delivered.
- `domain/policies.py` contains deterministic response suppression policy. The model cannot authorize a send or override AI/Human mode.
- `domain/catalog.py`, `domain/ranking.py`, `application/intent_extraction.py`, `application/catalog_search.py`, and `domain/shopping_state.py` separate catalog primitives, deterministic ranking, bounded intent extraction, tenant search, and persisted multi-turn state.
- `tools/recommendations.py` validates a closed set of recommendation/comparison inputs with `extra="forbid"`; callers cannot provide tenant IDs, SQL, or arbitrary tool names.
- The obsolete `app.services.ai_execution` compatibility facade has been deleted. Provider callers import from `app.features.ai.infrastructure.llm_gateway` and grounded graph callers from `app.features.ai.workflows.grounded_reply`. Other compatibility surfaces are retained only where still referenced.

## Safety and resource policy

Authorization and retrieval filters are deterministic application/database rules, never model decisions. Every execution and catalog query uses its authenticated organization ID. Sensitive order details are added only after the existing verified lookup flow. Model-extracted intent, conversation actions, and tool arguments are schema-validated and fall back or fail closed when invalid.

The provider gateway enforces the configured HTTP timeout, at most 2,048 output tokens per call, and per durable execution budgets of three model calls, 12,000 estimated prompt tokens, and 1,200 reserved completion tokens. The existing queue continues to cap active tenant executions and durable retries. Provider telemetry records model, elapsed time, and token counts without customer content. Output is constrained to bounded plain text; API schemas continue to omit prompts, instructions, encrypted context, and chain-of-thought.

Widget reply delivery is a two-step guard: an early stale-work check avoids unnecessary model calls, and the final transaction locks the conversation and rechecks mode, latest customer message, and teammate activity immediately before persistence. API-driven takeover uses the same conversation lock, so a late model result cannot override Human mode.

## Validation and limitations

Unit coverage includes invalid provider output, token-budget exhaustion, untrusted retrieved prompt content, malformed/extra tool arguments, and deterministic reply suppression. PostgreSQL integration coverage includes tenant isolation, concurrent active-execution limits, widget workflows, and the in-flight Human takeover race. Database-backed checks require `TEST_DATABASE_URL`; a skipped integration test is not evidence that database behavior passed.

Current text retrieval uses PostgreSQL full-text search over tenant chunks; there is no separate vector/RAG service. The worker still owns orchestration across execution kinds, but context assembly, policy/write paths, catalog extraction/search/ranking, and provider infrastructure now have focused modules. Future work can move each execution-kind orchestration into its own workflow when behavior diverges further; no checkpoint migration is needed for this split.
