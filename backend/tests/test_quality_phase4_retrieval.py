"""Focused Phase 4 retrieval regression checks."""

from types import SimpleNamespace

import pytest

from app.features.ai.application.retrieval_search import (
    _fast_relevance_boost,
    reciprocal_rank_fusion,
)


def test_title_and_content_overlap_boosts_relevance():
    relevant = SimpleNamespace(
        content="Refund requests are reviewed within seven days.",
        document_name="Refund policy",
        knowledge_base_name="Support",
    )
    unrelated = SimpleNamespace(
        content="Contact the store for opening hours.",
        document_name="Store hours",
        knowledge_base_name="Support",
    )
    terms = {"refund", "policy"}
    assert _fast_relevance_boost(terms, relevant) > _fast_relevance_boost(terms, unrelated)


def test_empty_terms_do_not_create_false_relevance():
    row = SimpleNamespace(content="Refund policy", document_name="Refund", knowledge_base_name="Support")
    assert _fast_relevance_boost(set(), row) == 0


def test_hybrid_rrf_rewards_both_retrieval_sources():
    assert reciprocal_rank_fusion(1, 1) > reciprocal_rank_fusion(1, None)


def test_rrf_rejects_invalid_ranks():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion(0, None)
