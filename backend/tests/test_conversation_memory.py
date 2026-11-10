"""Conversation topic memory regression tests."""
from app.features.ai.application.conversation_memory import derive_topic_memory
from app.features.ai.application.conversation_understanding import understand_conversation_turn


def test_topic_memory_ignores_assistant_and_acknowledgement() -> None:
    turns = [
        {"sender": "customer", "content": "What is your delivery fee?"},
        {"sender": "assistant", "content": "Which location?"},
        {"sender": "customer", "content": "okay"},
    ]
    memory = derive_topic_memory(turns)
    assert memory.active_topic == "delivery"
    assert memory.topic_anchor == "What is your delivery fee?"
    assert memory.last_customer_message == "okay"


def test_latest_explicit_topic_wins() -> None:
    turns = [
        {"sender": "customer", "content": "Refund policy?"},
        {"sender": "customer", "content": "What is the shipping fee?"},
    ]
    assert derive_topic_memory(turns).active_topic == "delivery"


def test_contextual_location_uses_topic_anchor() -> None:
    turns = [
        {"sender": "customer", "content": "How much is delivery?"},
        {"sender": "customer", "content": "okay"},
    ]
    result = understand_conversation_turn("for Kathmandu?", turns)
    assert "delivery" in result.retrieval_query.lower()


def test_empty_transcript_has_no_topic() -> None:
    memory = derive_topic_memory([])
    assert memory.active_topic is None
    assert memory.topic_anchor is None
