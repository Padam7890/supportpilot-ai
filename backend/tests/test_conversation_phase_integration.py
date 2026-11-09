"""Integration-level unit coverage for Phase 1-5 conversation and retrieval signals."""
from app.features.ai.application.conversation_understanding import understand_conversation_turn
from app.features.ai.application.evidence_assessment import assess_knowledge_evidence


def test_topic_memory_and_query_rewrite_are_connected() -> None:
    history = [
        {"sender": "customer", "content": "How much is delivery?"},
        {"sender": "assistant", "content": "Which city?"},
    ]
    result = understand_conversation_turn("for Kathmandu?", history)
    assert "Kathmandu" in result.retrieval_query
    assert "delivery" in result.retrieval_query


def test_evidence_signal_rejects_unrelated_excerpt() -> None:
    result = assess_knowledge_evidence(
        "refund policy", ["Our warehouse opens at nine."]
    )
    assert result.reason == "insufficient_lexical_overlap"


def test_evidence_signal_finds_candidate_not_verified_fact() -> None:
    result = assess_knowledge_evidence(
        "refund policy", ["Refund policy requests require review."]
    )
    assert result.reason == "lexical_candidate_only"
