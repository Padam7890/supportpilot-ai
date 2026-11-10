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
