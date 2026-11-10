# LLM-first Conversation Engine — Migration Tracker

**Status: Package 1 in progress. This PR is an opt-in foundation, not the complete agent refactor.**

## Target

Use a language model for open-ended conversation understanding and natural grounded replies. Keep deterministic authorization for order access, verification, cancellations, refunds, tenant isolation, and tool execution.

## Packages

1. **Opt-in model-first routing foundation** — implemented: `AI_CONVERSATION_LLM_FIRST_ENABLED=false` by default, shared interpretation policy, high-risk/negation/clarification protections, and policy regression scenarios.
2. Typed conversation agent input/output and bounded context — contracts implemented; runtime integration pending.
3. Typed tool registry, argument validation, and authorization — contracts and allowlist gate implemented; provider adapters pending.
4. Topic and unresolved-workflow memory with explicit verified/unverified separation — pending.
5. LLM response composition from trusted tool results — pending.
6. Semantic knowledge retrieval and Shopify catalog tool orchestration — pending.
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
