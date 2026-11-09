import json
from pathlib import Path

from app.features.ai.application.retrieval import build_retrieval_terms
from app.features.ai.application.retrieval_search import reciprocal_rank_fusion


def _load_corpus() -> list[dict[str, object]]:
    corpus_path = Path(__file__).with_name("corpus.json")
    return json.loads(corpus_path.read_text(encoding="utf-8"))


def test_rag_corpus_has_minimum_coverage():
    corpus = _load_corpus()
    assert len(corpus) >= 30
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
