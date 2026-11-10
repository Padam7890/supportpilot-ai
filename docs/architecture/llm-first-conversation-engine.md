# LLM-first Conversation Engine — Migration Tracker

**Status: Package 1 in progress. This PR is an opt-in foundation, not the complete agent refactor.**

## Target

Use a language model for open-ended conversation understanding and natural grounded replies. Keep deterministic authorization for order access, verification, cancellations, refunds, tenant isolation, and tool execution.

## Packages

1. **Opt-in model-first routing foundation** — implemented: `AI_CONVERSATION_LLM_FIRST_ENABLED=false` by default, shared interpretation policy, high-risk/negation/clarification protections, and policy regression scenarios.
2. Typed conversation agent input/output and bounded context — contracts and normalized context builder implemented; existing LLM router integrated.
3. Typed tool registry, argument validation, and authorization — contracts, allowlist, and adapter-based executor implemented; live provider adapters pending.
4. Topic and unresolved-workflow memory with explicit verified/unverified separation — pending.
5. LLM response composition from trusted tool results — standalone composer implemented; output grounding and live integration pending.
6. Semantic knowledge retrieval and Shopify catalog tool orchestration — tenant-scoped knowledge and catalog adapters implemented; live orchestration pending.
7. Streaming, latency and usage safeguards — pending.
8. Gradual removal of obsolete canned replies, rollout and rollback — pending.

## Important limitation of Package 1

The existing deterministic widget plan still has precedence for direct, sensitive, and verification workflows. The opt-in flag changes when the existing structured intent model is consulted; it **does not yet** turn the entire system into a tool-calling LLM agent or remove fixed replies. Model suggestions cannot authorize commerce actions. When the model is unavailable or invalid, the existing fallback remains.

## Local configuration

```dotenv
AI_CONVERSATION_LLM_FIRST_ENABLED=false
```

Enable only in a controlled development environment after reviewing model costs and routing behavior. Do not enable globally in production without behavioral verification. Tests and CI/CD have not been executed in this work session.

## Next increment: typed agent and tool boundary

- Added `conversation_agent_contracts.py` with bounded, validated message history and agent decisions.
- Added `conversation_tool_contracts.py` with typed tool requests and structured tool results.
- Added `conversation_tool_registry.py` with a server-controlled capability allowlist and explicit verification/side-effect checks.
- These are **contracts only**. They do not execute Shopify, retrieval, or support actions. A model-provided `verified_customer_id` must never be trusted: execution adapters must derive verified identity from server-side session state and enforce tenant ownership.
- Added focused regression scenarios; tests have not been executed.

## Increment: bounded context and guarded tool executor

- Added `conversation_context_builder.py` to normalize user/customer roles, exclude internal notes, bound history and avoid duplicate latest messages. The existing structured LLM router now uses this builder.
- Added `conversation_tool_executor.py` to pre-authorize the entire batch, cap calls at three, reject missing adapters, and validate returned tool identity. Providers are injected, not imported into the agent.
- Added targeted regression scenarios for context normalization, read-only execution, fail-closed authorization, and tool-call limits.
- **Important:** no live Shopify/order/handoff adapter is wired yet. Model-provided customer identifiers are untrusted; real adapters must obtain identity and tenant from authenticated server-side state and recheck permissions. No new side-effecting tool path is enabled.
- **Verification:** source changes committed; tests and CI/CD not executed. No production readiness claim.

## Increment: real read-only RAG adapter and response evidence

- Added `conversation_knowledge_adapter.py`, which calls the existing tenant- and AI-agent-scoped hybrid knowledge search using trusted server IDs. It exposes no tenant selection to the model.
- Added `conversation_response_evidence.py` to cap and normalize facts from authorized tools, ignore denied/unavailable facts, and carry source identifiers for downstream grounding.
- Added focused adapter and evidence regression scenarios.
- **Not yet live:** the worker is not switched to the new tool executor; Shopify catalog adapters and LLM response composition remain pending. This increment does not change production chatbot behavior.
- Tests/CI/CD not executed.

## Increment: catalog adapter and natural language composer

- Added `conversation_catalog_adapter.py` using existing tenant-filtered catalog candidates. It filters the catalog-wide fallback so unrelated products cannot be presented as matches. Current facts include title, brand, variant and availability; price/currency are intentionally omitted until exact money formatting is verified.
- Added `conversation_response_composer.py` to build bounded prompts with untrusted-history and tool-evidence boundaries and call the configured LLM gateway for natural replies.
- Added focused scenarios for unrelated catalog fallback and composer inputs.
- **Not live:** generated text must pass the existing grounding/claim validation and persistence controls before any customer delivery. The composer is not wired into the worker and is not production-ready. Tool selection and verification remain pending.
- Tests and CI/CD have not been executed.

## Increment: standalone LLM agent orchestration

- Added `conversation_agent_planner.py` for validated structured model planning of read-only knowledge and catalog requests.
- Added `conversation_agent.py` to orchestrate planning, pre-authorized tool execution, bounded evidence, LLM composition and numeric/citation grounding checks. No verified evidence for a requested tool means no answer is generated.
- Added isolated regression scenarios for authorized tool execution, rejected handoff, absent evidence and unsupported numeric claims.
- **Important limits:** this is not yet connected to the live widget/Playground worker or durable execution/persistence. Grounding currently performs lexical/numeric checks, not semantic entailment; unverified nonnumeric claims require stronger validation before rollout. Sensitive order/refund/handoff actions remain outside this agent. Planner and composer currently require two model calls when tools are used.
- Tests and CI/CD have not been executed.

## Increment: standalone composition root and answer-bypass guard

- Added `conversation_agent_runtime.py` to wire the structured planner, read-only agent orchestrator, tenant/agent-scoped knowledge adapter and tenant-scoped catalog adapter. The caller provides trusted IDs; the model cannot select tenant or bot.
- Added a deterministic safety backstop in `conversation_agent.py`: recognized product/order/refund, knowledge, or tool-requiring requests cannot be answered using the model-only `answer` route.
- Added regression scenarios for this bypass and ordinary greeting behavior.
- **This runtime is not invoked from the live widget or Playground worker.** The backstop is only as complete as the existing deterministic assessment; semantic grounding, missing-evidence UX, provider-cost budgets, and streaming must be addressed before rollout.
- Tests and CI/CD have not been executed.

## Increment: live worker pilot (first-contact greetings only)

- The widget worker now calls `try_complete_widget_agent_pilot` after existing follow-up checks and before deterministic turn routing. It is gated by `AI_CONVERSATION_LLM_FIRST_ENABLED` (default false).
- Only low-risk, standalone first-contact greetings qualify. Any previous substantive transcript, contextual follow-up, policy, product, order, refund, negation or multi-intent request stays on the legacy path. Existing stale-reply checks and `finish_widget_reply` handle persistence, draft-only mode, and delivery suppression.
- Invalid plans fall back to legacy routing. Unexpected provider errors use the worker's existing failure lifecycle. Output with numeric claims or over 500 characters is rejected by the pilot.
- **Do not enable for general customer traffic yet.** Semantic claim validation, tenant-specific bot tool permissions, end-to-end integration tests, streaming, and non-greeting migration remain pending. Flag-off behavior is unchanged.
- Tests and CI/CD have not been executed.

## Increment: pilot safety corrections

- Corrected an accidentally escaped multiline comment that had prevented the first-contact transcript guard from executing. The pilot now actually rejects previous substantive conversation turns.
- Corrected the numeric-claim regular expression and added regression scenarios for both guards.
- **No scope expansion:** live agent use remains first-contact greetings only, flag off by default. Strong semantic grounding, tool permission snapshots, end-to-end tests and safe wider migration are prerequisites to expanding traffic.
- Tests and CI/CD have not been executed.

## Increment: explicit tool permission enforcement

- The agent orchestrator no longer grants every read-only capability by default. `allowed_tools` defaults to an empty set and is intersected with the hard-coded read-only capability ceiling before execution.
- The standalone runtime now accepts an explicit server-provided tool allowlist; it also defaults to no tools. This prevents the model from searching catalog or knowledge unless the caller has authorized that capability.
- Updated tool-execution regression scenarios and added an unauthorized-catalog invocation test.
- **Next:** map existing AI bot tool snapshots to these capabilities and verify settings/tenant restrictions before expanding the widget pilot. The current greeting pilot does not grant tool access.
- Tests and CI/CD have not been executed.

## Increment: execution-scoped bot capability mapping

- Added `conversation_tool_permissions.py` with exact allowlisted mappings: `recommend_products` and `catalog_search` to catalog search; `knowledge_search` to knowledge search. Unknown, malformed, order, refund and handoff names grant nothing.
- The widget worker passes `execution.ai_agent_tools_snapshot` into the pilot. Missing snapshots grant no tools rather than silently trusting model requests or changing live bot permissions.
- Added permission-mapping regression scenarios. **No broader rollout:** the widget pilot remains first-contact greetings only and explicitly rejects tool-based responses. Future knowledge/catalog rollout must verify the actual persisted bot capability names and current authorization semantics.
- Tests and CI/CD have not been executed.

## Increment: default guarded pilot and legacy-model de-duplication

- `AI_CONVERSATION_LLM_FIRST_ENABLED` now defaults to **true**; setting it to `false` remains an immediate rollback switch. **Only standalone first-contact greetings** enter the new live agent. Commerce, RAG, catalog and follow-up workflows still use their existing guarded execution paths.
- Removed the old flag-driven forced model-first behavior in `intent_routing/service.py`, preventing a redundant legacy intent-model call for every low-risk non-agent turn. The existing confidence-based legacy router remains available as fallback, so this is not yet a complete removal of the old routing stack.
- Extracted the pilot's ad-hoc response checks into `conversation_greeting_policy.py`; the new policy rejects numbers, URLs, email addresses and common unverified store assertions. This is not semantic grounding and is not sufficient for broader customer traffic.
- Added focused output-policy tests. **No tests or CI/CD were run**. Before deployment, review environment overrides, provider costs and the pilot's routing/persistence behavior.

## Increment: stale execution race prevention

- The default first-contact widget agent pilot now checks execution freshness both before and after the model call. A newer customer message can supersede an execution during LLM latency; the old answer must not be persisted.
- Added a regression test simulating an execution becoming stale between the two checks.
- The new path is still restricted to first-contact greetings. **Do not delete legacy knowledge, commerce or follow-up execution yet**: those paths are not replaced by this pilot. Tests and CI/CD have not been executed.

## Increment: migrate knowledge-only answer composition

- `generate_guarded_draft` now uses the new bounded `compose_natural_answer` and `ResponseEvidence` for knowledge-only widget/playground runs **without custom instructions**. This replaces the old `create_grounded_draft` generation call for that subset, not retrieval, authorization or persistence.
- Existing tenant/bot-scoped retrieval, source citation checks at persistence, grounding validation, and widget lifecycle remain intact. Integration-backed responses, custom instructions and reply drafts still use `create_grounded_draft` until their contracts are migrated.
- Added regression tests for new composer selection, custom-instruction compatibility and unsupported numeric claims. Tests have not been executed.
- **Not a full RAG migration or safe blanket legacy deletion.** Remaining: instruction-aware composer, source provenance, citation/semantic grounding, integration-specific data boundaries, source freshness and end-to-end verification. Do not remove `create_grounded_draft` while it has active callers.

## Increment: instruction-aware knowledge generation migration

- The shared natural composer now accepts bounded, workspace-configured bot instructions as system-level configuration, distinct from untrusted history and retrieved evidence.
- Knowledge-only `widget_reply`, `playground`, and `reply_draft` executions now use the shared composer even when bot instructions are present.
- Integration-backed generation continues through `create_grounded_draft`; it cannot be removed safely until verified Shopify/order integration evidence is represented in typed, authorized tool results.
- Added regression cases for custom instructions, reply drafts, and integration isolation. Tests and CI/CD have not been executed. Grounding remains lexical, not semantic entailment.

## Increment: mandatory evidence citations on migrated RAG

- New knowledge-only RAG composer outputs must cite the provided bounded excerpts with `[source N]`. The composer prompt now uses matching evidence labels.
- Grounding checks run against **the exact excerpts provided to the model**, not a different or larger retrieval list. Missing citations, invalid citation indices and unsupported numeric claims fail closed to the existing safe fallback.
- Legacy integration-backed generation is deliberately not switched to this contract yet; it needs typed authorized integration evidence. Added regression cases for missing and invalid citations.
- This is lexical validation, **not semantic entailment**. Tests and CI/CD have not been executed.
