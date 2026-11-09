# Phase 11 — RAG accuracy and grounding

Tracking: [Production roadmap #10](https://github.com/Padam7890/supportpilot-ai/issues/10)

## Goal
Measure whether retrieved documents and final answers are actually correct and authorized, rather than assuming matching words mean a supported claim.

## Slice 1: implemented
- Pure, offline claim-to-excerpt candidate diagnostics, explicitly distinguishing `no_sources`, `no_lexical_candidate`, and `lexical_candidate_unverified`.
- Tests covering absent, irrelevant, and contradictory sources. Even a high lexical match is **never** certified as factually supported.
- No live answer blocking or additional LLM calls; avoids disrupting current widget traffic.

## Next slices (not implemented)
1. Create a labeled, source-versioned answer dataset with expected claims, citations and forbidden claims.
2. Run actual retrieval against seeded tenant fixtures; measure Recall@6, MRR and citation authorization.
3. Add a configurable grounded-answer verification policy with abstention and escalation on critical unsupported claims.
4. Compare reranking strategies and measure quality/latency/cost.
5. Integrate evaluation gates into CI and staging, including multilingual and malicious-source tests.

## Verification
```bash
cd backend
ruff check app/features/ai/application/claim_evidence_diagnostics.py tests/test_claim_evidence_diagnostics.py
pytest -q tests/test_claim_evidence_diagnostics.py tests/test_evidence_assessment.py
```

**Status:** Draft; tests not executed. This PR is an evaluation foundation, not a completed hallucination prevention system.
