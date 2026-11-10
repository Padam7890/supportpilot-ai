"""Phase 1: privacy-sensitive streaming context policy regression scenarios."""

from app.features.ai.application.stream_context_policy import (
    can_stream_transcript,
    stream_conversation_context,
)


def test_empty_history_is_eligible_for_context_filter() -> None:
    assert can_stream_transcript([]) is True
    assert stream_conversation_context("Hello", []) == []


def test_staff_message_is_never_exposed() -> None:
    history = [{"sender": "agent", "content": "Private customer order"}]
    assert can_stream_transcript(history) is False
    assert stream_conversation_context("Hello", history) == []


def test_contextual_follow_up_with_private_history_is_blocked() -> None:
    history = [{"sender": "assistant", "content": "Your order is private"}]
    assert can_stream_transcript(history) is False
    assert stream_conversation_context("What about that?", history) is None


def test_unmatched_assistant_message_is_not_social_context() -> None:
    history = [
        {"sender": "customer", "content": "Hi"},
        {"sender": "assistant", "content": "Your order number is 123"},
    ]
    assert can_stream_transcript(history) is False


def test_customer_only_history_is_not_assumed_safe() -> None:
    history = [{"sender": "customer", "content": "My order number is 123"}]
    assert can_stream_transcript(history) is True
    # A positive context-filter result is NOT authorization to publish the
    # customer transcript or any provisional generated text.
