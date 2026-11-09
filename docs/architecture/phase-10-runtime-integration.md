# Phase 10 — runtime integration of durable conversation topic state

Tracking: [Production hardening #10](https://github.com/Padam7890/supportpilot-ai/issues/10)

## Implemented
- The live widget execution context reads and records durable topic state in a tenant-scoped DB transaction.
- Explicit support topics are saved using compare-and-swap; a newer topic is not silently overwritten by an older version.
- Unanchored follow-ups can recover a safe topic label after recent transcript context falls out of the bounded window.
- New unrelated questions do not inherit the old topic.
- Late executions are prevented from writing a newer conversation's state by checking the latest customer message.
- ORM registration and schema constraints/indexes are aligned with migration 0074.
- Added focused tests for runtime topic resolution.

## Known limitations / required hardening
- No full workflow/task persistence, resumable order actions, or state-aware conversational routing yet. This integration improves the knowledge retrieval query path only.
- No state persistence for Playground sessions without a conversation ID.
- No end-to-end PostgreSQL RLS, migration, concurrency, retry, or browser tests executed yet.
- Concurrent writes can return a conflict; callers should measure and retry safely if required.
- Migration 0074 must be applied **before** deploying the worker using the table. Deploy schema first, then application.
- Expired rows are not automatically cleaned up; schedule retention cleanup after verifying tenant isolation.
- No OTP, identity, order references, or raw transcript are stored in topic state.

## Validation required
```bash
cd backend
ruff check app/features/ai/application/topic_state_runtime.py app/features/ai/application/context.py app/features/ai/application/durable_topic_state.py tests/test_topic_state_runtime.py
pytest -q tests/test_topic_state_runtime.py tests/test_durable_topic_state.py tests/test_conversation_phase_integration.py tests/test_ai_integration.py
alembic upgrade head
```

Run the full suite and staged two-tenant isolation tests before marking the PR ready.
