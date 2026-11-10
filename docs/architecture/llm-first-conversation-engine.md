# LLM-first conversation engine

SupportPilot runs Widget, AI Playground, and teammate reply drafts through the same intent contract, evidence model, composer, and semantic release gate. The durable PostgreSQL execution remains the owner of retries, permissions, and final writes.

## Execution boundaries

1. Load the tenant execution, active bot configuration, and bounded transcript. The Widget evaluates stale turns, pending questions, secure order workflows, and shopping state before generation. Playground previews sensitive next steps without executing them. Teammate drafts remain unsent.
2. Apply deterministic support and business policies before model routing. A single bounded intent call can classify an otherwise unknown standalone turn as general. Ambiguous follow-ups and explicit product, order, policy, and refund requests retain their evidence requirements. A model decision cannot authorize a tool, action, disclosure, or send.
3. Use the existing PostgreSQL keyword and pgvector retrieval for assigned, active knowledge bases. Evidence carries document and chunk identifiers and the exact bounded excerpt given to the composer. No matches use the missing-evidence path. Unauthorized sources are excluded and citations are rechecked before writing. Retrieval exceptions use the execution failure lifecycle instead of becoming empty catalogs or missing documents.
4. Generate one complete candidate. The composer treats conversation and source excerpts as untrusted data. A bounded structured semantic review evaluates each span, checks it for unsupported or contradictory facts, and requires matching citations and numeric/unit checks for store claims. Rejected, incomplete, malformed, or timed-out reviews suppress the candidate. Transient provider errors follow the worker’s existing retry policy. The per-execution model budget covers routing, composition, and review.
5. Persist only a reviewed answer or a deterministic safe response. Citation indices are remapped to the citations returned in the API. The Widget’s write checks the current source message, bot, teammate activity, and AI mode. SSE progressively replays eligible committed text after authorization checks.

## Evidence and commerce

- `ResponseEvidence` is the bounded evidence contract for knowledge excerpts, catalog display facts, and authorized order snapshots. Catalog recommendations and comparisons use deterministic prices, availability, and attributes from the existing tenant catalog and continue returning the existing product-card payload.
- The Widget still checks the unexpired OTP grant for the current conversation, then performs a tenant-scoped Shopify lookup and uses the deterministic order formatter. A number, an email typed in chat, or model output cannot supply that grant.
- Teammate order-assisted drafts use the server-authorized lookup tied to the conversation’s CRM customer. The encrypted snapshot retains approved status, exact amount and currency, cancellation, return, and bounded tracking fields. The draft renders those facts deterministically. A related policy answer can be generated separately from verified knowledge. The order snapshot, contacts, addresses, tokens, and tracking URLs are excluded from both model calls.
- Refunds and cancellations stay with the existing human-review workflows. The model has no commerce mutation tools.

## Retired paths and replacements

| Removed | Replacement |
| --- | --- |
| `widget_agent_pilot.py`, `conversation_agent.py`, `conversation_agent_runtime.py`, `conversation_agent_planner.py`, and `conversation_greeting_policy.py` | Existing deterministic social and sensitive routes plus shared intent routing and guarded composition |
| Prototype catalog and knowledge adapters, and prototype tool contracts, executor, permission mapper, and registry | Existing tenant-scoped retrieval and catalog services and the allowlisted recommendation tool schemas |
| `workflows/grounded_reply.py` and `infrastructure/checkpoints.py` | Durable `AIExecution` worker, shared composer, and semantic release gate. Existing checkpoint rows and migrations are retained. |
| `app.services.ai_execution` compatibility facade, removed in PR #34 | Direct imports from the relevant AI application or provider modules |
| Source-less and provisional lexical release helpers | Full-candidate semantic review with required per-span source and number checks |

## Branch reconciliation

GitHub had already squash-merged PR #34 at `7b24b28`. Its conflict resolution retained the shared composer and bounded order evidence, fixed the malformed Shopify exception handler, and preserved deterministic Shopify output. The follow-up uses that commit as its base. Existing retrieval, embedding, and chunking migrations were outside this change.

## Rollout and rollback

`AI_CONVERSATION_LLM_FIRST_ENABLED` controls the intent model’s ability to classify otherwise unknown general turns. Disabling it restores conservative missing-knowledge handling for those turns. The semantic release gate remains mandatory. `WIDGET_AI_STREAMING_ENABLED` controls committed-text playback. Disable it to use normal history polling.

The semantic reviewer is probabilistic. It can reject good answers or miss subtle claims. It has no authority over order or financial facts, and review adds a provider call and latency for generated replies. Measure multilingual entailment, false rejection, per-tenant cost, and end-to-end delivery in staging before wider release. A rollback to the earlier build restores its weaker generation checks, so prefer pausing automated replies while investigating a release issue.

Tests and CI were not run for this migration at the project owner’s request.
