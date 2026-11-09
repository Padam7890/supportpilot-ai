"""Deterministic RAG evaluation helpers (no fabricated scores)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvalCase:
    id: str
    question: str
    category: str
    context: list[str]
    expected_doc_terms: list[str]
    expected_route: str
    skip_semantic: bool
    skip_retrieval: bool
    forbidden_claims: list[str]


def load_eval_corpus(path: Path | None = None) -> list[EvalCase]:
    corpus_path = path or Path(__file__).resolve().parents[4] / "tests" / "rag_eval" / "corpus.json"
    raw: list[dict[str, Any]] = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []
    for item in raw:
        cases.append(
            EvalCase(
                id=str(item["id"]),
                question=str(item["question"]),
                category=str(item.get("category", "general")),
                context=[str(line) for line in item.get("context", []) if isinstance(line, str)],
                expected_doc_terms=[
                    str(term) for term in item.get("expected_doc_terms", []) if str(term)
                ],
                expected_route=str(item.get("expected_route", "knowledge")),
                skip_semantic=bool(item.get("skip_semantic", False)),
                skip_retrieval=bool(item.get("skip_retrieval", False)),
                forbidden_claims=[
                    str(claim) for claim in item.get("forbidden_claims", []) if str(claim)
                ],
            )
        )
    return cases


def reciprocal_rank(rank: int | None) -> float:
    if rank is None or rank < 1:
        return 0.0
    return 1.0 / rank


def recall_at_k(relevant: set[str], ranked: list[str], k: int = 6) -> float:
    if not relevant:
        return 1.0
    hits = len(relevant & set(ranked[:k]))
    return hits / len(relevant)


def precision_at_k(relevant: set[str], ranked: list[str], k: int = 6) -> float:
    if k <= 0:
        return 0.0
    window = ranked[:k]
    if not window:
        return 0.0
    hits = sum(1 for item in window if item in relevant)
    return hits / len(window)


def mean_reciprocal_rank(relevant: set[str], ranked: list[str]) -> float:
    for index, item in enumerate(ranked, start=1):
        if item in relevant:
            return reciprocal_rank(index)
    return 0.0
