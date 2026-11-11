# Knowledge gaps: staged implementation

This draft PR introduces the conservative classification and FAQ suggestion
policy only. **It is now connected to the widget worker as a diagnostic event, but not to database persistence or dashboard.**
The worker emits `ai_knowledge_gap_candidate_detected` for qualifying post-generation outcomes. Early missing-evidence returns are not yet covered. Do not claim automatic collection until persistence and grouping are implemented.

## Intended workflow

1. After a customer-facing knowledge retrieval, emit a structured outcome
   `no_relevant_evidence`, `retrieved`, or another explicit outcome.
2. Classify only knowledge questions whose retrieval found no relevant evidence
   or whose answer failed grounding. Do not classify greetings, order status,
   commerce operations, model outages or generic refusal text as gaps.
3. Persist one tenant-scoped occurrence per source message with a unique key,
   avoiding retries double-counting. Do not log sensitive customer content.
4. Group semantically similar questions **within the same tenant** using
   embedding similarity with a configurable threshold, and provide a way for
   humans to split or merge incorrect groups. Do not use hardcoded keyword
   matching as the semantic grouping engine.
5. Show grouped count, latest occurrence, representative question and source
   conversation links in the existing Knowledge dashboard.
6. Generate a review-only FAQ suggestion. Never generate an unsupported
   delivery promise, refund rule or other policy. An answer must be supplied
   or verified by an authorized owner/admin.
7. Publish via the existing knowledge ingestion pipeline only after approval,
   then re-embed and verify retrieval for the affected bot knowledge bases.

## Required before merge

- Add tenant-scoped persistence, unique occurrence constraints, indexes, and
  RLS policies with Alembic migration.
- Extend the initial worker diagnostic hook to cover early missing-evidence returns and replace the temporary evidence-required intent proxy with a dedicated structured knowledge-intent outcome. No parsing of response wording.
- Implement tenant-scoped semantic grouping and review APIs.
- Add the dashboard review and publish workflow.
- Add PostgreSQL integration tests for tenant isolation, duplicate events,
  authorization and approval; test bot-specific retrieval after publishing.
- Run backend and frontend test suites. This draft has not been executed.

The policy code intentionally has no direct side effects so it can be tested
and integrated without risking customer-facing behavior.
