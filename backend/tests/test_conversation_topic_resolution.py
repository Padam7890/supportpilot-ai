"""Regression cases for customer topic changes and contextual retrieval."""
from app.features.ai.application.conversation_understanding import understand_conversation_turn


def _turn(content: str) -> dict[str, str]:
    return {"sender": "customer", "content": content}


def test_location_follow_up_inherits_delivery_topic() -> None:
    result = understand_conversation_turn(
        "for Kathmandu?",
        [_turn("How much is delivery?")],
    )
    assert result.contextual_follow_up
    assert "delivery" in result.retrieval_query.lower()
    assert "Kathmandu" in result.retrieval_query


def test_acknowledgement_does_not_replace_active_topic() -> None:
    result = understand_conversation_turn(
        "for Kathmandu?",
        [_turn("How much is delivery?"), _turn("okay")],
    )
    assert "delivery" in result.retrieval_query.lower()


def test_explicit_new_topic_does_not_inherit_refund_context() -> None:
    result = understand_conversation_turn(
        "what about shipping?",
        [_turn("What is the refund policy?")],
    )
    assert result.topic_switch
    assert "refund" not in result.retrieval_query.lower()


def test_short_pronoun_follow_up_uses_last_explicit_topic() -> None:
    result = understand_conversation_turn(
        "how about that?",
        [_turn("What is your warranty policy?"), _turn("thanks")],
    )
    assert "warranty" in result.retrieval_query.lower()


def test_standalone_question_does_not_inherit_history() -> None:
    result = understand_conversation_turn(
        "Do you accept credit cards?",
        [_turn("What is your return policy?")],
    )
    assert result.retrieval_query == "Do you accept credit cards?"
