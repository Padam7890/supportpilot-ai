# Conversation Engine V2 — Phase 1 Tracker

**Branch:** `refactor/conversation-v2-phase1-foundation`  
**PR:** https://github.com/Padam7890/supportpilot-ai/pull/31 (draft)  
**Status:** In progress. CI/CD remediation deferred at developer request.  
**Progress:** 10 of 11 tracked work packages implemented in code (not a production-readiness score).

| Work package | State | Implementation |
| --- | --- | --- |
| Repair malformed Python source | Implemented | `intent_routing/service.py`, `retrieval_search.py` |
| Separate stream context policy | Implemented | `stream_context_policy.py` |
| Extract execution lifecycle | Implemented | `execution_lifecycle.py` |
| Extract failure/retry decisions | Implemented | `execution_failure_policy.py` |
| Extract widget routing, order, and refund follow-ups | Implemented | `widget_turn_routing.py`, `widget_sensitive_execution.py`, `widget_follow_up_execution.py` |
| Extract Playground routing and inventory | Implemented | `playground_routing.py`, `playground_execution.py` |
| Extract shared guarded generation and no-evidence policy | Implemented | `guarded_generation.py`, `missing_evidence_policy.py` |
| Extract widget failure fallback policy | Implemented | `widget_failure_fallback.py` |
| Extract non-widget generated answer persistence | Implemented | `generated_reply_persistence.py` revalidates tenant, active agent and sources before commit |
| Extract remaining error persistence / retry orchestration | Implemented | `execution_failure_persistence.py` owns tenant-scoped retry/failure transactions |
| Run targeted runtime verification and fix compatibility regressions | Pending | Added tests are not confirmed passing |
| Final architecture review and Phase 1 merge decision | Pending | Do not merge draft PR without review |

## Important constraints

- Phase 1 is an architectural refactor, **not** proof of 100% conversation accuracy or production readiness.
- Widget and Playground currently buffer generated output until grounding checks complete. True progressive streaming belongs to a later phase.
- Preserve tenant isolation, verified-order authorization, source checks, and safe escalation.
- CI/CD pipeline cleanup is explicitly out of scope for now. Targeted local/runtime checks remain necessary.
- Keep this tracker updated after every Phase 1 code change.

## Latest implementation note

Failure persistence and retry transitions now use `persist_execution_failure`. The worker retains exception diagnostics and last-resort widget handoff. Phase 1 remains **not complete** until focused runtime verification, import checks, and architecture review; CI/CD cleanup is deferred, not the correctness gate.
