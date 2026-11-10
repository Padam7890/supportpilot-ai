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


def test_negated_cancellation_widget_never_routes_to_sensitive() -> None:
    from app.features.ai.application.conversation_orchestration import plan_widget_turn

    plan = plan_widget_turn("Don't cancel my order", [])
    assert plan.route == "direct"
    assert plan.intent == "negated_action"


def test_negated_cancellation_playground_never_routes_to_order_follow_up() -> None:
    from app.features.ai.application.conversation_orchestration import plan_playground_turn

    plan = plan_playground_turn(
        "Don't cancel my order",
        [{"sender": "assistant", "content": "Please verify your order to continue."}],
    )
    assert plan is not None
    assert plan.intent == "negated_action"


def test_unrelated_previous_customer_message_does_not_become_topic_anchor() -> None:
    result = understand_conversation_turn(
        "what about that?",
        [{"sender": "customer", "content": "Hello there"}],
    )
    assert result.needs_clarification is True
    assert result.retrieval_query == "what about that?"
