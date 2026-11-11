import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.features.ai.application.follow_up import (
    PENDING_KEY,
    PENDING_TTL,
    assess_widget_follow_up,
    order_verification_question,
    pending_from_assistant,
    refund_start,
    resolve_follow_up,
)
from app.features.ai.application.policy_follow_up import FollowUpInterpretation

_ITEM = FollowUpInterpretation(relation="answer_to_question", goal="refund_item", confidence=0.99)
_DAMAGED = FollowUpInterpretation(
    relation="answer_to_question", goal="refund_reason", refund_reason="damaged", confidence=0.99,
)
_MISSING_ORDER = FollowUpInterpretation(
    relation="answer_to_question", goal="none", action_target="order",
    order_reference_status="unavailable", confidence=0.99,
)
_NEW_MISSING_ORDER = _MISSING_ORDER.model_copy(update={"relation": "new_topic"})
_CONFIRM_REFUND = FollowUpInterpretation(
    relation="answer_to_question", goal="none", confirmation="affirm",
    action_target="refund_request", confidence=0.99,
)
_CONFIRM_HANDOFF = FollowUpInterpretation(
    relation="answer_to_question", goal="none", confirmation="affirm",
    action_target="human_support", confidence=0.99,
)


def test_refund_context_survives_serialization_and_requires_verification():
    now = datetime.now(UTC)
    bot_id, item_message_id, verification_id = uuid4(), uuid4(), uuid4()
    start, _ = assess_widget_follow_up(
        "I want a refund.", [], agent_id=bot_id, source_message_id=uuid4(), now=now
    )
    assert start and start.pending
    reason = resolve_follow_up(
        "actually, broken", start.pending, source_message_id=uuid4(),
        interpretation=FollowUpInterpretation(
            relation="answer_to_question", goal="refund_reason", refund_reason="damaged", confidence=0.99,
        ),
    )
    assert reason and reason.pending and reason.pending.refund_reason == "damaged"
    assert "Which item" in reason.draft
    state = pending_from_assistant(
        {"sender": "assistant", PENDING_KEY: json.dumps(reason.pending.attached_to(bot_id, now))},
        bot_id,
        now,
    )
    assert state is not None
    item = resolve_follow_up("Two blue mugs", state, source_message_id=item_message_id, interpretation=_ITEM.model_copy(update={"item_text": "Two blue mugs"}))
    assert item and item.pending and item.pending.item_message_id == item_message_id
    assert item.pending.verification_status == "required"
    premature_yes = resolve_follow_up("yes", item.pending, source_message_id=uuid4(), interpretation=_CONFIRM_REFUND)
    assert premature_yes and premature_yes.review is None
    assert resolve_follow_up("123456", item.pending, source_message_id=uuid4()) is None

    review_state = item.pending.model_copy(
        update={
            "stage": "refund_review",
            "expected_answer_type": "confirmation",
            "verification_status": "verified",
            "verification_id": verification_id,
        }
    )
    review = resolve_follow_up("yes", review_state, source_message_id=uuid4(), interpretation=_CONFIRM_REFUND)
    assert review and review.review == review_state
    declined = resolve_follow_up(
        "cancel it", review_state, source_message_id=uuid4(),
        interpretation=_CONFIRM_REFUND.model_copy(update={"confirmation": "retract"}),
    )
    assert declined and declined.decision == "declined" and declined.review is None


@pytest.mark.parametrize("prompt", [
    "What’s the reason for your refund?",
    "Could you describe what happened to the item?",
    "¿Qué le pasó al artículo?",
])
def test_follow_up_uses_state_independently_of_assistant_wording(prompt):
    now, bot_id = datetime.now(UTC), uuid4()
    turn = {
        "sender": "assistant", "content": prompt, "created_at": now.isoformat(),
        PENDING_KEY: json.dumps(refund_start().attached_to(bot_id, now)),
    }
    result, reason = assess_widget_follow_up(
        "damaged", [turn], agent_id=bot_id, source_message_id=uuid4(), now=now,
        interpretation=_DAMAGED,
    )
    assert result and result.decision == "refund_reason"
    assert reason == "resolved"
    turn.pop(PENDING_KEY)
    assert assess_widget_follow_up(
        "damaged", [turn], agent_id=bot_id, source_message_id=uuid4(), now=now,
        interpretation=_DAMAGED,
    )[0] is None


@pytest.mark.parametrize(
    "message",
    [
        "Track my order #1001",
        "What is your refund policy?",
        "delivery charges",
        "hello",
        "Compare these products",
    ],
)
def test_unrelated_turn_does_not_fill_pending_refund_item(message):
    now, bot_id = datetime.now(UTC), uuid4()
    result = resolve_follow_up("damaged", refund_start(), source_message_id=uuid4(), interpretation=_DAMAGED)
    assert result and result.pending
    turn = {"sender": "assistant", PENDING_KEY: json.dumps(result.pending.attached_to(bot_id, now))}
    assert (
        assess_widget_follow_up(
            message, [turn], agent_id=bot_id, source_message_id=uuid4(), now=now
        )[0]
        is None
    )


def test_pending_question_rejects_wrong_bot_expiration_and_human_takeover():
    now, bot_id = datetime.now(UTC), uuid4()
    turn = {"sender": "assistant", PENDING_KEY: json.dumps(refund_start().attached_to(bot_id, now))}
    assert pending_from_assistant(turn, uuid4(), now) is None
    assert pending_from_assistant(turn, bot_id, now + PENDING_TTL) is None
    assert pending_from_assistant({**turn, "sender": "agent"}, bot_id, now) is None
    assert pending_from_assistant({"sender": "assistant", "content": "Here is the refund policy."}, bot_id, now) is None


def test_multi_word_delivery_synonym_is_encoded_as_a_phrase():
    from app.features.ai.application.retrieval import build_keyword_tsquery, build_retrieval_terms

    terms = build_retrieval_terms("delivery charges")
    assert "estimated delivery" in terms
    assert '"estimated delivery"' in build_keyword_tsquery(terms)


@pytest.mark.parametrize(
    "question",
    [
        "I forget the order number",
        "I can't find my order reference",
        "I don’t know the order ID",
        "My order number is missing",
    ],
)
def test_missing_order_reference_starts_with_recovery_and_support(question):
    result, reason = assess_widget_follow_up(
        question, [], agent_id=uuid4(), source_message_id=uuid4(), now=datetime.now(UTC),
        interpretation=_NEW_MISSING_ORDER,
    )
    assert reason == "started"
    assert result and result.pending and result.pending.order_number_unavailable
    assert result.pending.verification_status == "required"
    assert result.draft and "confirmation email" in result.draft and "support team" in result.draft
    assert not result.handoff


def test_persisted_order_slot_resolves_short_reply():
    from app.services.widget_ai import ORDER_VERIFICATION_MESSAGE

    now, bot_id = datetime.now(UTC), uuid4()
    history = [
        {"sender": "customer", "content": "I forget the order number"},
        {
            "sender": "assistant",
            "content": ORDER_VERIFICATION_MESSAGE,
            "created_at": now.isoformat(),
            PENDING_KEY: json.dumps(order_verification_question().attached_to(bot_id, now)),
        },
    ]
    answer = "sorry i forget number"
    assert (
        assess_widget_follow_up(
            answer, [], agent_id=bot_id, source_message_id=None, now=now,
            interpretation=_MISSING_ORDER,
        )[0]
        is None
    )
    result, reason = assess_widget_follow_up(
        answer, history, agent_id=bot_id, source_message_id=None, now=now,
        interpretation=_MISSING_ORDER,
    )
    assert result and result.pending and result.pending.order_number_unavailable
    assert reason == "resolved"
    assert "Enter the order number" not in result.draft


def test_missing_order_state_handles_decline_repeated_request_and_correction():
    from app.features.ai.application.follow_up import resolve_order_support

    initial = resolve_order_support("I lost my order number", interpretation=_NEW_MISSING_ORDER)
    assert initial and initial.pending
    declined = resolve_follow_up(
        "no", initial.pending, source_message_id=uuid4(),
        interpretation=_CONFIRM_HANDOFF.model_copy(update={"confirmation": "deny"}),
    )
    assert declined and declined.pending and declined.pending.handoff_status == "declined"
    repeated = resolve_follow_up(
        "what is my order status", declined.pending, source_message_id=uuid4()
    )
    assert repeated and repeated.pending and repeated.pending.order_number_unavailable
    assert repeated.draft and "Enter the order number" not in repeated.draft
    for message in ("What is your refund policy?", "Recommend a blue mug"):
        assert resolve_follow_up(message, repeated.pending, source_message_id=uuid4()) is None
    handoff = resolve_follow_up("yes", repeated.pending, source_message_id=uuid4(), interpretation=_CONFIRM_HANDOFF)
    assert handoff and handoff.pending and handoff.handoff
    again = resolve_follow_up(
        "sorry i forget number", handoff.pending, source_message_id=uuid4(), interpretation=_MISSING_ORDER,
    )
    assert again and not again.handoff
    reference_message_id = uuid4()
    corrected = resolve_follow_up(
        "I found it, #1001", handoff.pending, source_message_id=reference_message_id
    )
    assert corrected and corrected.pending and not corrected.pending.order_number_unavailable
    assert corrected.pending.order_reference_message_id == reference_message_id
    assert corrected.pending.verification_id is None
    assert corrected.pending.verification_status == "required"


def test_interrupted_refund_verification_preserves_collected_item_and_reason():
    item_id = uuid4()
    damaged = resolve_follow_up("damaged", refund_start(), source_message_id=uuid4(), interpretation=_DAMAGED)
    assert damaged and damaged.pending
    item = resolve_follow_up("Blue mug", damaged.pending, source_message_id=item_id, interpretation=_ITEM.model_copy(update={"item_text": "Blue mug"}))
    assert item and item.pending
    interrupted = resolve_follow_up(
        "My code expired", item.pending, source_message_id=uuid4(),
        interpretation=FollowUpInterpretation(relation="unclear", goal="none", confidence=0.99),
    )
    assert interrupted and interrupted.pending == item.pending
    assert interrupted.draft and "fresh code" in interrupted.draft
    missing = resolve_follow_up(
        "I cannot find my order number", item.pending, source_message_id=uuid4(),
        interpretation=_MISSING_ORDER,
    )
    assert missing and missing.pending and missing.pending.order_number_unavailable
    assert missing.pending.refund_reason == "damaged" and missing.pending.item_message_id == item_id
    assert resolve_follow_up("Actually, I found it", missing.pending, source_message_id=uuid4()) is None
    resumed = resolve_follow_up("Actually, I found it: #1001", missing.pending, source_message_id=uuid4())
    assert resumed and resumed.pending and resumed.pending.stage == "refund_verification"
    assert resumed.pending.verification_status == "required"
