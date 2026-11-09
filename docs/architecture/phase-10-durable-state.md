# Phase 10 — durable conversation state

Tracking: [Roadmap #10](https://github.com/Padam7890/supportpilot-ai/issues/10)

## Slice 1 (this PR)
- Add `conversation_topic_states` table with tenant and conversation composite FK, agent FK, forced PostgreSQL RLS, TTL and version.
- Store only a constrained topic label, not user messages, OTP codes, customer identifiers or verification grants.
- Provide tenant-scoped reads and compare-and-swap writes; a stale version fails instead of silently overwriting a newer turn.
- Add isolated repository unit tests.

## Not yet integrated
The current conversation runtime still derives topic context from recent messages. The new table is **not** read or written by the widget worker yet. Do not advertise durable memory as operational until a follow-up PR integrates state lifecycle with widget and Playground and tests concurrency, expiration, tenant isolation and agent changes.

## Required verification
```bash
cd backend
ruff check app/features/ai/application/durable_topic_state.py tests/test_durable_topic_state.py migrations/versions/0074_conversation_topic_state.py
pytest -q tests/test_durable_topic_state.py
alembic upgrade head
python scripts/assert_runtime_db_role.py
```

Verify PostgreSQL RLS with two tenants, and check downgrade behavior on staging before deployment. No commands have been run as part of this PR.
