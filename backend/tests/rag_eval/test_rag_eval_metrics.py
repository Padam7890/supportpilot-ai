import json
from pathlib import Path

import pytest

from app.features.ai.application.rag_eval import (
    load_eval_corpus,
    mean_reciprocal_rank,
    precision_at_k,
    recall_at_k,
)
from app.features.ai.application.retrieval import build_retrieval_terms, should_skip_semantic_retrieval
from app.features.ai.application.retrieval_search import reciprocal_rank_fusion


def _load_corpus() -> list[dict[str, object]]:
    corpus_path = Path(__file__).with_name("corpus.json")
    return json.loads(corpus_path.read_text(encoding="utf-8"))


def test_rag_corpus_has_minimum_coverage():
    corpus = _load_corpus()
    assert len(corpus) >= 50
    categories = {str(item["category"]) for item in corpus}
    assert "refunds" in categories
    assert "shipping" in categories
    assert "greeting" in categories
    assert "injection" in categories


def test_retrieval_terms_expand_support_intents_for_corpus_questions():
    corpus = _load_corpus()
    for item in corpus:
        question = str(item["question"])
        expected_terms = {term.casefold() for term in item["expected_doc_terms"]}
        if not expected_terms:
            continue
        expanded = set(build_retrieval_terms(question))
        assert expected_terms & {term.casefold() for term in expanded}, question


def test_rrf_prefers_overlap_between_keyword_and_semantic_ranks():
    direct = reciprocal_rank_fusion(1, 1)
    split = reciprocal_rank_fusion(1, None) + reciprocal_rank_fusion(None, 2)
    assert direct > split


def test_greetings_skip_semantic_retrieval():
    for question in ("Hello", "Thanks!", "नमस्ते"):
        assert should_skip_semantic_retrieval(question)


def test_eval_metric_helpers_are_deterministic():
    relevant = {"doc-a", "doc-b"}
    ranked = ["doc-b", "doc-x", "doc-a", "doc-y", "doc-z", "doc-a"]
    assert recall_at_k(relevant, ranked, k=6) == 1.0
    assert precision_at_k(relevant, ranked, k=3) == pytest.approx(2 / 3)
    assert mean_reciprocal_rank(relevant, ranked) == 1.0


def test_load_eval_corpus_matches_json_file():
    cases = load_eval_corpus(Path(__file__).with_name("corpus.json"))
    assert len(cases) >= 50
    assert any(case.category == "recommendation" for case in cases)
