# Conversation Engine V2 — Phase 1 foundation

## Changes
- Repair invalid literal escaped newline tokens in intent routing and hybrid retrieval Python modules.
- Extract pure stream-context privacy checks from the large worker into `features/ai/application/stream_context_policy.py`, preserving worker compatibility imports.
- Add targeted stream-context policy regressions for staff messages, unmatched assistant replies, contextual follow-ups, and empty history.

## Current architectural boundaries
- `services/ai_worker.py` remains the durable execution coordinator; it still contains substantial routing and delivery logic.
- `application/intent_routing` chooses candidate routes but cannot authorize commerce actions.
- `application/stream_context_policy` screens provisional conversation history; it does **not** authorize emitting generated text.
- `infrastructure/llm_gateway.py` owns provider communication.
- Existing claim grounding, tenant checks and persisted reply delivery remain unchanged.

## Remaining Phase 1 decomposition work
- Move widget-specific turn orchestration out of the worker into an application service with explicit dependencies.
- Move playground turn orchestration to the same application boundary.
- Extract durable execution state transitions and failure handling behind typed interfaces.
- Consolidate overlapping deterministic conversation rules without changing security-sensitive precedence.
- Validate imports, compile all backend modules and inspect CI results before merging.

## Local verification
From `backend`:

```bash
python -m compileall -q app
pytest -q tests/test_stream_context_policy.py tests/test_intent_router.py tests/test_claim_grounding.py
```

No passing execution result has been verified through the GitHub connector. Keep this pull request draft until checks are complete.
