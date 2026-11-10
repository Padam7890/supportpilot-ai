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

## Manual compatibility review — latest pass

- Inspected worker delegation, guarded generation, Playground routing, missing-evidence policy, sensitive order support, and verified refund follow-up.
- Fixed a verified refund review path that returned `completed=True` without persisting any result when its retrieval context disappeared. It now raises a typed exception so the worker's existing failure handling runs rather than silently stranding the execution.
- Added a targeted regression scenario for the missing-context path.
- **Verification limitation:** This is a source-level review, not a successful runtime test. GitHub checkout in the execution environment failed due to DNS/network resolution, so imports and tests remain unverified. The tracker stays at 10/11; Phase 1 is not complete.

## Compatibility fixes — follow-up review

- Verified refund missing-context exceptions now declare `knowledge_retrieval` as their failure stage. The worker accepts only explicit known stage labels, avoiding misleading generic failure diagnostics.
- Guarded generation no longer persists the string `"None"` when the model provider omits its model name. Added a regression scenario.
- The architecture extraction packages remain implemented, but runtime verification and final review are still pending. No CI/CD pipeline work or merge was performed.
