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


def test_pending_prompt_survives_intervening_customer_turn() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.features.ai.application.follow_up import PENDING_KEY, refund_start

    agent_id = uuid4()
    now = datetime.now(UTC)
    pending = refund_start().attached_to(agent_id, now)
    import json
    transcript = [
        {"sender": "assistant", "content": "Was the item damaged?", PENDING_KEY: json.dumps(pending)},
        {"sender": "customer", "content": "Could you repeat that?"},
    ]
    result = understand_conversation_turn("It was damaged", transcript, agent_id=agent_id, now=now)
    assert result.pending_state is not None
    assert result.pending_state.stage == "refund_reason"


def test_new_explicit_topic_does_not_inherit_old_pending_refund_slot() -> None:
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.features.ai.application.follow_up import PENDING_KEY, assess_widget_follow_up, refund_start
    import json

    agent_id = uuid4()
    now = datetime.now(UTC)
    transcript = [
        {"sender": "assistant", "content": "Was the item damaged?", PENDING_KEY: json.dumps(refund_start().attached_to(agent_id, now))},
    ]
    result, status = assess_widget_follow_up(
        "What are your delivery charges?", transcript, agent_id=agent_id,
        source_message_id=None, now=now,
    )
    assert result is None
    assert status == "no_matching_pending_question"


def test_multiple_support_subjects_detected() -> None:
    result = understand_conversation_turn(
        "Where is my order and what is your refund policy?", []
    )
    assert result.multi_intent is True


def test_unrelated_single_subject_not_multi_intent() -> None:
    result = understand_conversation_turn("What is your delivery policy?", [])
    assert result.multi_intent is False
