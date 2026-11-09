import pytest

from app.features.ai.application.conversation_orchestration import (
    plan_playground_turn,
    plan_widget_turn,
    playground_missing_knowledge_reply,
)
from app.features.ai.application.conversational_intents import classify_conversational_intent


@pytest.mark.parametrize(
    "message",
    [
        "hey whats up",
        "are you there?",
        "what is your name?",
        "how are you?",
        "can you help me?",
        "Hello!",
        "नमस्ते",
    ],
)
def test_social_messages_route_without_knowledge(message: str):
    assert classify_conversational_intent(message) is not None
    playground = plan_playground_turn(message)
    assert playground is not None
    assert playground.route == "direct"
    widget = plan_widget_turn(message, [])
    assert widget.route == "direct"
    assert widget.draft


def test_mixed_greeting_and_policy_still_needs_knowledge():
    assert classify_conversational_intent("hey, what's your refund policy?") is None
    assert plan_playground_turn("hey, what's your refund policy?") is None
    assert plan_widget_turn("hey, what's your refund policy?", []).route == "knowledge"


def test_playground_missing_knowledge_distinguishes_follow_up():
    reply = playground_missing_knowledge_reply("What about that?")
    assert "which topic" in reply.casefold() or "detail" in reply.casefold()


def test_widget_sensitive_route_for_order_question():
    plan = plan_widget_turn("Where is my order #1234?", [])
    assert plan.route == "sensitive"
    assert plan.reply_status == "escalated"
