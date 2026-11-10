"""Phase 2 regression coverage for multi-subject conversational turns."""

from app.features.ai.application.conversation_understanding import (
    understand_conversation_turn,
)


def test_shipping_and_refund_are_separate_intents() -> None:
    result = understand_conversation_turn(
        "What is the shipping policy and refund policy?", []
    )
    assert result.multi_intent is True


def test_single_subject_is_not_multi_intent() -> None:
    result = understand_conversation_turn(
        "What is the shipping policy?", []
    )
    assert result.multi_intent is False


def test_semicolon_separates_distinct_support_subjects() -> None:
    result = understand_conversation_turn(
        "Tell me about shipping; what is the refund policy?", []
    )
    assert result.multi_intent is True


def test_negated_cancellation_is_not_treated_as_contextual_follow_up() -> None:
    result = understand_conversation_turn(
        "Don't cancel my order",
        [{"sender": "customer", "content": "Please cancel order 123"}],
    )
    assert result.correction is True
    assert result.negated_action is True
    assert result.topic_switch is True
    assert result.retrieval_query == "Don't cancel my order"


def test_nepali_script_signal() -> None:
    result = understand_conversation_turn("मेरो सामान फिर्ता", [])
    assert result.language in {"ne", "mixed"}


def test_bounded_follow_up_does_not_invent_prior_context() -> None:
    result = understand_conversation_turn("and what about that?", [])
    assert result.retrieval_query == "and what about that?"
