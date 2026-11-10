# Conversation Engine V2 — Phase 2: Unified Understanding

**Status:** In progress. Phase 1 is merged; Phase 2 changes are isolated on a new branch.

## Goal

Interpret customer turns consistently across widget and Playground without changing working order authorization, refund verification, or knowledge grounding. Prioritize existing behavior and introduce improvements in small, reviewable increments.

## Work packages

| Package | Status |
| --- | --- |
| 1. Repair multi-clause detection and protect existing routing | Implemented |
| 2. Normalize and classify corrections, negations, and topic switches | Implemented (advisory signals) |
| 3. Resolve contextual follow-ups with bounded topic history | Existing bounded resolver reused; deeper review pending |
| 4. Represent multiple intents without executing multiple actions | Shared advisory signal implemented; final review pending |
| 5. Improve ambiguous references and clarification decisions | Pending |
| 6. Support English, Nepali, and mixed messages safely | Existing language detector reused; language-specific review pending |
| 7. Integrate understanding consistently into widget and Playground | Shared router metadata implemented |
| 8. Review latency, routing costs, and safe fallback paths | Pending |
| 9. Final code-level consolidation | Pending |

## First change

Fixed the clause separator regex: it previously matched literal backslash-s text instead of whitespace. A message such as "shipping policy and refund policy" can now be split into distinct subjects for advisory multi-intent classification. Added targeted regression scenarios.

**Safety invariant:** Classification is advisory. No inferred intent may bypass order verification, trigger refunds/cancellations, or turn conversation history into trusted evidence.

**Verification:** Tests and CI/CD are deferred by owner request. No runtime pass is claimed.

## Current branch changes

- Repaired multi-clause whitespace separator and added regression scenarios.
- Added explicit correction and negated-commerce-action signals to the typed understanding result. These signals are advisory and never authorize an order or refund action.
- Integrated the same bounded understanding metadata into the common intent routing service used by widget and Playground. No additional LLM call was introduced.
- Preserved existing deterministic action routing and verification precedence; no model-inferred commerce execution is enabled.
- Added regression scenarios for negated cancellation, Nepali script detection and a context-free follow-up.

**Remaining:** Clarification behavior, language-specific cases, follow-up edge cases, latency review and final consolidation. Do not mark Phase 2 complete before these are reviewed. Tests and CI/CD were not executed, per request.

## Additional implementation — action safety and bounded follow-ups

- Both Playground and widget now resolve explicitly negated commerce requests to a deterministic non-action reply **before** sensitive-order or pending-order follow-up handling. No cancellation, refund, or return action is initiated by that route.
- Follow-up query resolution no longer treats arbitrary prior customer text (such as a greeting) as an actionable topic anchor. It requires an explicit recognized prior topic, otherwise asks for clarification.
- Understanding input is bounded to 1,000 characters before rule-based parsing. This does not replace upstream request-size validation.
- Added regression scenarios for negative cancellation in both channels and for an unrelated prior greeting.

**Still outstanding before completing Phase 2:** review nuanced correction/negation phrasing, multi-intent routing conflicts, multilingual cases, and end-to-end behavior. The PR remains draft. No tests or CI/CD were run.
