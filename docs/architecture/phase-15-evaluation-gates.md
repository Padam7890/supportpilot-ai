# Phase 15 — automated AI evaluation gates

Tracking: [Production hardening roadmap #10](https://github.com/Padam7890/supportpilot-ai/issues/10)

## Implemented
- Added a deterministic evaluation-corpus integrity gate to the existing backend CI workflow.
- Validates minimum 100 labeled cases, required coverage for refunds, shipping, products, follow-ups, orders, and prompt injection, unique IDs, non-empty questions, and internally consistent skip-retrieval expectations.
- Added regression tests for duplicate cases, missing coverage, and contradictory expectations.
- Verified from the committed corpus data that it currently contains **112 cases** across 16 categories, with no duplicate IDs or contradictory skip-retrieval expectations.

## Critical distinction
Passing this gate **does not** prove RAG correctness. It validates the quality of the *evaluation dataset*. Live retrieval Recall@6, citation validity, tenant isolation, answer factuality, and unsupported-claim rates are **not measured** by this gate. Do not approve production based on it.

## CI and local execution
```bash
cd backend
python scripts/rag_release_gate.py
pytest -q tests/test_rag_release_gate.py
ruff check app/features/ai/application/rag_release_gate.py scripts/rag_release_gate.py tests/test_rag_release_gate.py
```

## Next
1. Seed a deterministic multi-tenant knowledge fixture and label expected document IDs.
2. Evaluate actual retrieval outputs (Recall@6, MRR) rather than term overlap.
3. Evaluate answer citations and unsupported claims using independently labeled expected evidence.
4. Fail staging release on measured threshold violations, with auditable reports.
5. Expand to 150–200 verified labeled scenarios including order security, multilingual and contradictory policy.

**Status:** CI wiring committed; CI and tests not executed here.
