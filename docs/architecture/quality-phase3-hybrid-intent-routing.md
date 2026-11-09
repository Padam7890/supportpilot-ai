# Quality Phase 3 — Hybrid intent routing

## Scope delivered on this branch

- Preserve deterministic-first routing and optional structured LLM classification.
- Validate structured intent enums, bounded confidence, and reject duplicate intent predictions.
- Use configured low-confidence threshold to request clarification when a model is uncertain.
- Reject model-proposed tool-dependent order/refund routing when the deterministic assessment did not require tools.
- Prevent a model-only order prediction from converting a knowledge question into a sensitive commerce route.
- Retain deterministic multi-intent detection and metrics on provider failures.
- Preserve safe deterministic fallback when provider output is invalid or unavailable.

## Safety boundaries

Routing predictions are advisory, never identity proof or authorization. Commerce workers must continue enforcing tenant context, verification, permissions, approval and idempotency. This phase does not execute multiple commerce actions or validate store policies.

## Verification

Added focused tests in `backend/tests/test_intent_router.py`. These tests were not executed in this session; CI and runtime outcomes remain unverified. Run `cd backend && pytest -q tests/test_intent_router.py` and the full suite before production release.
