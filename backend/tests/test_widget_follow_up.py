import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.features.ai.application.follow_up import (
    PENDING_KEY,
    PENDING_TTL,
    assess_widget_follow_up,
    infer_assistant_question,
    pending_from_assistant,
    refund_start,
    resolve_follow_up,
)


def test_refund_context_survives_serialization_and_requires_verification():
    now = datetime.now(UTC)
    bot_id, item_message_id, verification_id = uuid4(), uuid4(), uuid4()
    start, _ = assess_widget_follow_up(
        "I want a refund.", [], agent_id=bot_id, source_message_id=uuid4(), now=now
    )
    assert start and start.pending
    reason = resolve_follow_up("actually, broken", start.pending, source_message_id=uuid4())
    assert reason and reason.pending and reason.pending.refund_reason == "damaged"
    assert "Which item" in reason.draft
    state = pending_from_assistant(
        {"sender": "assistant", PENDING_KEY: json.dumps(reason.pending.attached_to(bot_id, now))},
        bot_id,
        now,
    )
    assert state is not None
    item = resolve_follow_up("Two blue mugs", state, source_message_id=item_message_id)
    assert item and item.pending and item.pending.item_message_id == item_message_id
    assert item.pending.verification_status == "required"
    premature_yes = resolve_follow_up("yes", item.pending, source_message_id=uuid4())
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
    review = resolve_follow_up("yes", review_state, source_message_id=uuid4())
    assert review and review.review == review_state
    declined = resolve_follow_up("cancel it", review_state, source_message_id=uuid4())
    assert declined and declined.decision == "declined" and declined.review is None


@pytest.mark.parametrize(
    ("prompt", "answer", "decision", "route"),
    [
        (
            "What's the reason for your refund—change of mind or damaged/defective/incorrect?",
            "damaged",
            "refund_reason",
            None,
        ),
        (
            "Was the item damaged, defective, incorrect, or did you change your mind?",
            "wrong item",
            "refund_reason",
            None,
        ),
        (
            "Would you like me to track your order?",
            "yes",
            "order_confirmation",
            "Where is my order?",
        ),
        ("Should I check the order?", "cancel it", "order_confirmation", "Please cancel my order"),
        ("Would you like me to cancel your order?", "no", "declined", None),
        (
            "Which product would you like an alternative for?",
            "the second one",
            "product_reference",
            "the second one",
        ),
        (
            "When would you like it delivered?",
            "tomorrow",
            "policy_timing",
            "Store delivery policy for the requested time: tomorrow",
        ),
    ],
)
def test_short_follow_ups_use_the_previous_assistant_question(prompt, answer, decision, route):
    now = datetime.now(UTC)
    result, reason = assess_widget_follow_up(
        answer,
        [
            {"sender": "assistant", "content": prompt, "created_at": now.isoformat()},
            {"sender": "customer", "content": answer},
        ],
        agent_id=uuid4(),
        source_message_id=uuid4(),
        now=now,
    )
    assert result and result.decision == decision and result.routed_question == route
    assert reason == "resolved"


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
    result = resolve_follow_up("damaged", refund_start(), source_message_id=uuid4())
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
    assert infer_assistant_question("Here is the refund policy.") is None


def test_multi_word_delivery_synonym_is_encoded_as_a_phrase():
    from app.features.ai.application.retrieval import build_keyword_tsquery, build_retrieval_terms

    terms = build_retrieval_terms("delivery charges")
    assert "estimated delivery" in terms
    assert '"estimated delivery"' in build_keyword_tsquery(terms)
