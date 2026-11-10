"""Phase 1 conversation understanding contract tests."""
from app.features.ai.application.conversation_understanding import understand_conversation_turn


def test_english_question_has_typed_intents() -> None:
    result = understand_conversation_turn("What is your refund policy?", [])
    assert result.language == "en"
    assert result.candidate_intents
    assert not result.needs_clarification


def test_nepali_script_language_signal() -> None:
    result = understand_conversation_turn("मलाई डेलिभरी चाहिन्छ", [])
    assert result.language == "ne"


def test_romanized_nepali_signal() -> None:
    result = understand_conversation_turn("mero order kaha cha", [])
    assert result.language in {"ne", "mixed"}


def test_mixed_language_signal() -> None:
    result = understand_conversation_turn("mero order delivery status?", [])
    assert result.language == "mixed"


def test_unresolved_pronoun_requests_clarification() -> None:
    result = understand_conversation_turn("what about that?", [])
    assert result.contextual_follow_up
    assert result.needs_clarification


def test_follow_up_with_context_does_not_request_clarification() -> None:
    result = understand_conversation_turn(
        "what about that?",
        [{"sender": "customer", "content": "What is the warranty policy?"}],
    )
    assert not result.needs_clarification
