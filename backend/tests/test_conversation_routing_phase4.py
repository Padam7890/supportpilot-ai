"""Phase 4: scoped casual chat and safe clarification routing."""
from app.features.ai.application.conversation_orchestration import (
    plan_playground_turn,
    plan_widget_turn,
)
from app.features.ai.application.conversational_intents import classify_conversational_intent


def test_off_topic_question_is_not_sent_to_knowledge() -> None:
    result = plan_widget_turn("tell me a joke", [])
    assert result.route == "direct"
    assert result.intent == "off_topic"


def test_support_question_with_greeting_is_not_swallowed() -> None:
    assert classify_conversational_intent("hello, what is your refund policy?") is None


def test_unknown_context_asks_clarification() -> None:
    result = plan_widget_turn("what about that?", [])
    assert result.route == "clarification"


def test_playground_unknown_context_asks_clarification() -> None:
    result = plan_playground_turn("what about that?", [])
    assert result is not None
    assert result.route == "clarification"


def test_explicit_policy_request_keeps_knowledge_route() -> None:
    assert plan_widget_turn("what about shipping?", []).route == "knowledge"
