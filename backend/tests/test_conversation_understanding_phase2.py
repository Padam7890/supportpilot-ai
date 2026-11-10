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


def test_compound_negation_is_not_silently_accepted_as_whole_turn() -> None:
    result = understand_conversation_turn(
        "Don't cancel my order and tell me about delivery", []
    )
    assert result.negated_action is False


def test_standalone_negative_refund_is_non_action() -> None:
    from app.features.ai.application.conversation_orchestration import plan_widget_turn

    plan = plan_widget_turn("Do not refund my order", [])
    assert plan.intent == "negated_action"


def test_short_contextual_delivery_location_uses_bounded_anchor() -> None:
    result = understand_conversation_turn(
        "in Pokhara?",
        [{"sender": "customer", "content": "What are the delivery fees?"}],
    )
    assert result.needs_clarification is False
    assert "Pokhara" in result.retrieval_query


def test_new_topic_does_not_inherit_old_topic() -> None:
    result = understand_conversation_turn(
        "What about warranty?",
        [{"sender": "customer", "content": "Tell me about delivery"}],
    )
    assert result.topic_switch is True
    assert "delivery" not in result.retrieval_query.casefold()


def test_requested_handoff_does_not_repeat_on_new_product_question() -> None:
    from app.features.ai.application.follow_up import (
        order_verification_question,
        resolve_order_support,
    )

    pending = order_verification_question().model_copy(
        update={"order_number_unavailable": True, "handoff_status": "requested"}
    )
    assert resolve_order_support("do you have a mobile phone?", pending) is None
    assert resolve_order_support("store team doesnt follow me", pending) is None


def test_unresolved_order_handoff_allows_new_product_subject() -> None:
    from app.features.ai.application.follow_up import (
        order_verification_question,
        resolve_order_support,
    )

    pending = order_verification_question().model_copy(
        update={"order_number_unavailable": True, "handoff_status": "offered"}
    )
    assert resolve_order_support("do you have a mobile phone?", pending) is None


def test_mobile_phone_question_routes_to_knowledge_not_handoff() -> None:
    from app.features.ai.application.conversation_orchestration import plan_widget_turn

    assert plan_widget_turn("do you have a mobile phone?", []).route == "knowledge"
