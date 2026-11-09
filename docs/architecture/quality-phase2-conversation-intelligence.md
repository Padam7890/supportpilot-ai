# Quality Phase 2 — Conversation intelligence

## Implemented in PR #22

- Correction-aware query rewriting: a new or negated instruction does not inherit stale retrieval anchors.
- Negative commerce requests cannot initiate a positive refund/cancellation follow-up flow.
- Latest delivered assistant prompt can be recovered across intervening customer turns; agent binding and expiry remain enforced by `pending_from_assistant`.
- Explicit new subjects are not treated as short refund-slot answers.
- Multi-clause, multi-subject turns are flagged for downstream handling. This flag never authorizes tools.
- Added regression tests for context, retraction, topic changes, pending recovery and multiple subjects.

## Safety and boundaries

- Conversation topic hints and user messages are not identity proof or commerce authorization.
- This phase does not automatically revoke an action already submitted to Shopify. Those require their own workflow state transitions.
- Existing tenant-scoped durable topic storage and CAS remain in use; no new migration is required.
- This is a deterministic conversation-understanding improvement, not a guarantee of semantic accuracy for every language or phrasing.

## Validation status

- Tests were added but **not executed** in this GitHub-editing session, at the user's request not to wait for them.
- CI, browser, migration and production integration outcomes are **unverified**.
- Before a production release, run `cd backend && pytest -q tests/test_conversation_corrections.py tests/test_topic_state_runtime_regressions.py`, the full backend suite, and the existing widget browser tests.

## Follow-on scope (Phase 3, not Phase 2)

- Structured LLM intent router with confidence thresholds and calibration.
- Multi-intent action planning and ordered execution with per-action authorization.
- Wider Nepali/romanized language intent evaluation.
