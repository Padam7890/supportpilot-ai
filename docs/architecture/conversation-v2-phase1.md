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
- Extract failure classification, retry scheduling and terminal failure persistence behind typed interfaces. Lease claiming and deterministic completion now live in `application/execution_lifecycle.py`.
- Consolidate overlapping deterministic conversation rules without changing security-sensitive precedence.
- Validate imports, compile all backend modules and inspect CI results before merging.

## Local verification
From `backend`:

```bash
python -m compileall -q app
pytest -q tests/test_stream_context_policy.py tests/test_intent_router.py tests/test_claim_grounding.py
```

No passing execution result has been verified through the GitHub connector. Keep this pull request draft until checks are complete.

## Additional implementation (continuation)

- Moved tenant-scoped execution claiming, exhausted-lease failure transitions and deterministic completion into `features/ai/application/execution_lifecycle.py`.
- Preserved imports in `services/ai_worker.py` so existing worker call sites continue using the same function names and signatures.
- Removed unused worker lease-policy and SQL expression imports after extraction.
- Kept all existing row locks, tenant filters, status checks, field clearing and commit behavior intact.

**Important:** Phase 1 is still open: the main execution function remains large, and worker failure handling and widget/playground orchestration are not yet fully extracted. Do not treat this PR as ready to merge without review and verification.

## Failure handling extraction

- Added `application/execution_failure_policy.py` with immutable `FailureAssessment` and `RetryDecision` contracts.
- Worker now delegates error-code normalization, provider HTTP status extraction, retry exhaustion, retry delays, and widget fallback eligibility to pure policy functions.
- Added `tests/test_execution_failure_policy.py` for provider errors, retrieval errors, retry exhaustion, non-retryable errors, widget fallback and invalid attempts.
- Database writes and customer-facing fallback persistence remain in the worker for now. This change does not implement true streaming or a unified widget/playground engine.
- Compilation and test execution remain unverified; run `python -m compileall -q app` and `pytest -q tests/test_execution_failure_policy.py tests/test_stream_context_policy.py` before merging.

## Widget routing coordinator extraction

- Added `application/widget_turn_routing.py` with typed `WidgetRouteResult`.
- Preserved existing follow-up routing precedence, optional structured LLM routing, and router diagnostic events.
- Updated the worker to delegate route selection while keeping secure order verification, refund review, catalog processing, and reply persistence in their existing locations.
- Added `tests/test_widget_turn_routing.py` covering follow-up bypass and ordinary intent routing.
- This is **not** a complete widget orchestration extraction; sensitive workflows still require a separate application service and explicit dependency boundaries.

## Playground inventory extraction

- Added `application/playground_execution.py` to own tenant-scoped knowledge inventory lookup and deterministic persistence.
- The worker now delegates inventory requests to this application service; no LLM call is required for inventory listings.
- Supports missing agent selection (`UUID | None`) and retains existing row locks and execution state guards.
- Worker is reduced further; full playground conversation orchestration and sensitive widget flows are still pending.
- No local Python compilation or test run was executed in this connector-only editing session.

## Sensitive widget route extraction

- Added `application/widget_sensitive_execution.py` for verified order lookup, cancellation review messaging, and verification prompts.
- The service explicitly rejects non-sensitive routes and does not execute order mutations, refunds, or cancellations.
- Existing verified Shopify order lookup and reply persistence are reused, retaining tenant/conversation identifiers.
- Added focused scenarios for unverified cancellation and invalid route dispatch.
- Refund follow-up review and shopping paths remain in the worker. Integration and compilation are not yet verified.

## Refund follow-up extraction

- Added `application/widget_follow_up_execution.py` with an explicit `FollowUpCompletion` result, preserving existing pending question and escalation behavior.
- Verified refund requests remain staff-review requests only; no refund is issued automatically.
- If verification is missing or expired, the flow asks for OTP verification rather than treating an earlier message as authorization.
- Worker retains the routing stage diagnostic and delegates follow-up completion to the new service.
- Added focused tests for OTP requirement and nonterminal follow-up routing.

## Verification status

GitHub CI was queued when checked on commit `4d5acc942fb7f89a2fe186327d4407f04da2719a`. No passing check or local runtime verification has been established. Keep the PR in draft until failures (if any) are resolved.

## CI investigation (November 10)

GitHub Actions run `42739905056` for the phase branch reported backend Ruff failure (99 findings repository-wide) and frontend ESLint failure (six errors). Backend Ruff included unrelated existing files such as `app/workers/handlers/automation.py` (undefined `execution`), plus import-order findings and unused compatibility imports in `ai_worker.py`. Follow-up commit explicitly exports compatibility worker symbols and removes unused settings/timedelta imports. This does not resolve repository-wide CI failures. Do not merge without a green check or a reviewed baseline comparison. Direct local checkout was unavailable in this environment.

## Playground conversation routing separation

- Added `application/playground_routing.py` for deterministic-first preview routing and optional structured intent classification.
- Worker now delegates Playground turn selection while retaining shared generation, grounding, and persistence boundaries.
- Added targeted tests for deterministic preview and model-router fallback.
- Per developer preference, CI/CD cleanup is deferred during the testing phase; this does not mean runtime checks are passing. Local smoke tests and real conversation scenarios remain important before release.
