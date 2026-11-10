"""Deterministic release gate for the labeled RAG evaluation corpus.

This gate checks dataset integrity and scenario coverage only. It does not
pretend to measure live retrieval recall, citations, or LLM correctness.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.features.ai.application.rag_eval import load_eval_corpus

REQUIRED_CATEGORIES = frozenset({"refunds", "shipping", "product", "follow_up", "order", "injection"})
MIN_CASES = 100


@dataclass(frozen=True)
class CorpusGateResult:
    passed: bool
    count: int
    categories: dict[str, int]
    failures: tuple[str, ...]


def evaluate_corpus_gate(path: Path | None = None) -> CorpusGateResult:
    cases = load_eval_corpus(path)
    failures: list[str] = []
    counts = Counter(case.category for case in cases)
    if len(cases) < MIN_CASES:
        failures.append(f"corpus_too_small:{len(cases)}<{MIN_CASES}")
    missing = REQUIRED_CATEGORIES - counts.keys()
    if missing:
        failures.append("missing_categories:" + ",".join(sorted(missing)))
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        failures.append("duplicate_case_ids")
    for case in cases:
        if not case.id.strip() or not case.question.strip():
            failures.append(f"empty_id_or_question:{case.id!r}")
        if not case.category.strip():
            failures.append(f"empty_category:{case.id}")
        if case.skip_retrieval and case.expected_doc_terms:
            failures.append(f"contradictory_retrieval_expectation:{case.id}")
    return CorpusGateResult(
        passed=not failures,
        count=len(cases),
        categories=dict(sorted(counts.items())),
        failures=tuple(failures),
    )
