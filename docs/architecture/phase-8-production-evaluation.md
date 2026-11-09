# Phase 8 — production evaluation and release gates

## Automated checks

Run from the repository root:

```bash
cd backend
pytest -q tests/test_conversation_understanding.py \
  tests/test_conversation_phase_integration.py \
  tests/test_conversation_phase8_matrix.py \
  tests/test_conversation_routing_phase4.py \
  tests/test_evidence_assessment.py \
  tests/test_order_action_policy.py \
  tests/test_widget_follow_up.py \
  tests/test_widgets_unit.py \
  tests/test_ai_integration.py
cd ../frontend
node --check public/supportpilot-widget.js
```

## Staging release gates

1. **Tenant isolation:** Verify that conversation history, retrieval sources,
   OTP grants, and order actions cannot cross organization boundaries.
2. **Order workflows:** Test OTP success, wrong code, expiration, retries,
   revoked access, wrong conversation, Shopify disconnect, cancellation review,
   and refund continuation. Never execute a mutation without merchant approval.
3. **RAG grounding:** Evaluate absent, contradictory, stale, and malicious
   documents. Lexical overlap is only a diagnostic, not a proof of support.
4. **Multi-turn behavior:** Test topic switches, pronouns, corrections,
   multiple intents, Nepali and Romanized Nepali; include ambiguous requests.
5. **Streaming:** Confirm actual incremental SSE arrival, progressive DOM paint,
   reconnect without duplicate deltas, handoff, failure and retry behavior.
6. **Performance:** Record first provider token, Redis publish, browser delta,
   first DOM update and final response by execution ID. Establish latency SLOs
   from real measurements rather than invented thresholds.
7. **Operations:** Confirm redaction of personal information, bounded retries,
   rate limiting, alerting and rollback via streaming feature flag.

## Current coverage limits

The parameterized matrix provides deterministic unit-level checks. It does
not establish production readiness, 100 independent real-world conversations,
model answer correctness, or end-to-end Shopify and browser behavior.
All checks must run in CI/staging and failures must be addressed before launch.
