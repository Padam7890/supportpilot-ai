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


def test_negated_cancellation_does_not_start_order_action() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.features.ai.application.follow_up import assess_widget_follow_up

    follow_up, status = assess_widget_follow_up(
        "Don't cancel my order", [], agent_id=uuid4(),
        source_message_id=None, now=datetime.now(UTC),
    )
    assert status == "retracted"
    assert follow_up is not None
    assert follow_up.decision == "declined"
    assert follow_up.routed_question is None
    assert follow_up.pending is None


def test_retraction_stops_pending_cancellation() -> None:
    from app.features.ai.application.follow_up import order_verification_question, resolve_follow_up

    follow_up = resolve_follow_up(
        "Wait, don't cancel it", order_verification_question(action="cancel"),
        source_message_id=None,
    )
    assert follow_up is not None
    assert follow_up.decision == "declined"
    assert follow_up.pending is None
