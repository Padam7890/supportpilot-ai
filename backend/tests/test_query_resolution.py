"""Standalone contextual query rewriting regression tests."""
from app.features.ai.application.query_resolution import resolve_retrieval_query


def test_delivery_location_query_is_standalone() -> None:
    result = resolve_retrieval_query(
        "for Kathmandu?", topic_anchor="How much is delivery?",
        active_topic="delivery", contextual=True, explicit_topic=False,
    )
    assert "delivery" in result
    assert "Kathmandu" in result
    assert "How much" not in result


def test_explicit_topic_switch_does_not_inherit_history() -> None:
    assert resolve_retrieval_query(
        "what about shipping?", topic_anchor="refund policy",
        active_topic="refund", contextual=True, explicit_topic=True,
    ) == "what about shipping?"


def test_missing_context_does_not_hallucinate() -> None:
    assert resolve_retrieval_query(
        "what about that?", topic_anchor=None, active_topic=None,
        contextual=True, explicit_topic=False,
    ) == "what about that?"


def test_receipt_follow_up_inherits_return_policy() -> None:
    result = resolve_retrieval_query(
        "without a receipt?", topic_anchor="What is the return policy?",
        active_topic="refund", contextual=True, explicit_topic=False,
    )
    assert "return policy" in result
    assert "receipt" in result
