"""Conversation correction regression tests for phase two."""

from app.features.ai.application.conversation_understanding import understand_conversation_turn


def test_customer_correction_does_not_inherit_refund_topic() -> None:
    transcript = [{"sender": "customer", "content": "What is your refund policy?"}]
    result = understand_conversation_turn("Actually, I want delivery information", transcript)
    assert result.topic_switch is True
    assert result.contextual_follow_up is False
    assert "refund policy" not in result.retrieval_query.lower()


def test_short_follow_up_still_preserves_context() -> None:
    transcript = [{"sender": "customer", "content": "What is your refund policy?"}]
    result = understand_conversation_turn("What about after 10 days?", transcript)
    assert result.contextual_follow_up is True
    assert result.topic_switch is False
    assert "refund" in result.retrieval_query.lower()


def test_do_not_cancel_is_treated_as_correction() -> None:
    transcript = [{"sender": "customer", "content": "Cancel my order"}]
    result = understand_conversation_turn("Don't cancel it", transcript)
    assert result.topic_switch is True
    assert result.contextual_follow_up is False
    assert "cancel my order" not in result.retrieval_query.lower()
