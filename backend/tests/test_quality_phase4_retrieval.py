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


@pytest.mark.parametrize(
    ("query", "relevant_excerpt", "irrelevant_excerpt"),
    [
        (
            "refund policy",
            "Customers may request a refund under the return policy.",
            "The store opens Monday through Friday.",
        ),
        (
            "shipping fee",
            "Shipping fees and delivery charges depend on destination.",
            "Warranty repairs require an inspection.",
        ),
        (
            "product warranty",
            "The product warranty covers manufacturing defects.",
            "Order tracking is available from your account.",
        ),
    ],
)
def test_support_retrieval_reranker_prefers_relevant_excerpt(
    query: str, relevant_excerpt: str, irrelevant_excerpt: str
):
    from app.features.ai.application.retrieval import build_retrieval_terms

    terms = set(build_retrieval_terms(query))
    relevant = SimpleNamespace(
        content=relevant_excerpt, document_name="Support guide",
        knowledge_base_name="Help",
    )
    irrelevant = SimpleNamespace(
        content=irrelevant_excerpt, document_name="Support guide",
        knowledge_base_name="Help",
    )
    assert _fast_relevance_boost(terms, relevant) > _fast_relevance_boost(terms, irrelevant)


def test_explicit_new_topic_never_inherits_previous_retrieval_anchor():
    from app.features.ai.application.query_resolution import resolve_retrieval_query

    question = "What is your warranty policy?"
    assert resolve_retrieval_query(
        question, topic_anchor="refund policy", active_topic="refund",
        contextual=False, explicit_topic=True,
    ) == question


def test_contextual_delivery_location_uses_active_topic_without_policy_claim():
    from app.features.ai.application.query_resolution import resolve_retrieval_query

    result = resolve_retrieval_query(
        "in Pokhara?", topic_anchor="How much is delivery?",
        active_topic="delivery", contextual=True, explicit_topic=False,
    )
    assert "Pokhara" in result
    assert "shipping" in result
    assert "refund" not in result
