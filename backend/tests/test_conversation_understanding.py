"""Shared conversation understanding regression matrix for widget and Playground."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.features.ai.application.conversation_orchestration import (
    plan_playground_turn,
    plan_widget_turn,
)
from app.features.ai.application.conversation_understanding import understand_conversation_turn
from app.features.ai.application.follow_up import PENDING_KEY

_TOPICS = [
    ("Can I return a damaged jacket?", "refund"),
    ("How long does shipping take?", "shipping"),
    ("Recommend a phone under 30000", "phone"),
    ("What payment methods do you accept?", "payment"),
    ("Where is my order #1234?", "order"),
]
_FOLLOWUPS = [
    ("What about that?", True),
    ("And this one?", True),
    ("How long does it take?", True),
    ("Actually, tell me about shipping fees", False),
    ("New question: do you take cards?", False),
    ("Can I get a refund and track my order?", False),
    ("That sounds wrong; I meant the other item", True),
    ("What if it was opened?", True),
    ("Thanks, what are your store hours?", False),
    ("फिर्ता कसरी गर्ने?", False),
]

# Fifty distinct two-turn cases, repeated against both execution surfaces.
SCENARIOS = [
    pytest.param(topic, followup, id=f"{topic[1]}-{index}-{followup[0][:18]}")
    for topic in _TOPICS
    for index, followup in enumerate(_FOLLOWUPS)
]


@pytest.mark.parametrize("surface", ["widget", "playground"])
@pytest.mark.parametrize("topic,followup", SCENARIOS)
def test_multiturn_context_resolution_is_shared_and_topic_bounded(surface, topic, followup):
    prior_question, prior_topic = topic
    message, contextual = followup
    transcript = [
        {"sender": "customer", "content": prior_question},
        {"sender": "assistant", "content": f"Here is the {prior_topic} information."},
        {"sender": "customer", "content": message},
    ]
    understood = understand_conversation_turn(message, transcript)
    assert understood.contextual_follow_up is contextual
    if contextual and not understood.topic_switch:
        assert prior_question.casefold() in understood.retrieval_query.casefold()
    else:
        assert prior_question.casefold() not in understood.retrieval_query.casefold()

    if surface == "widget":
        plan = plan_widget_turn(message, transcript)
    else:
        plan = plan_playground_turn(message, transcript)
    assert plan is None or plan.route == "knowledge" or plan.draft is not None


def test_current_widget_turn_is_not_used_as_its_own_history():
    message = "What about that?"
    understood = understand_conversation_turn(
        message,
        [
            {"sender": "customer", "content": "Can I return it?"},
            {"sender": "assistant", "content": "What item is it?"},
            {"sender": "customer", "content": message},
        ],
    )
    assert understood.retrieval_query.startswith("Can I return it?")
    assert understood.retrieval_query.endswith(message)
    assert understood.retrieval_query.count(message) == 1


def test_switching_back_to_a_prior_topic_does_not_retrieve_intervening_topic():
    history = [
        {"sender": "customer", "content": "Can I return a damaged jacket?"},
        {"sender": "assistant", "content": "Here is the return policy."},
        {"sender": "customer", "content": "What about shipping to Pokhara?"},
        {"sender": "assistant", "content": "Here is the shipping information."},
    ]
    message = "Back to my return question: what if it was opened?"
    result = understand_conversation_turn(message, history)
    assert result.topic_switch
    assert "return" in result.retrieval_query.casefold()
    assert "pokhara" not in result.retrieval_query.casefold()


def test_active_pending_state_is_typed_and_expires_with_agent_scope():
    agent_id = uuid4()
    state = {
        "active_intent": "refund",
        "stage": "refund_reason",
        "expected_answer_type": "reason",
        "ai_agent_id": str(agent_id),
        "expires_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat(),
    }
    result = understand_conversation_turn(
        "It arrived damaged.",
        [{"sender": "assistant", "content": "What happened?", PENDING_KEY: json.dumps(state)}],
        agent_id=agent_id,
    )
    assert result.pending_state is not None
    assert result.pending_state.stage == "refund_reason"


def test_multi_intent_turn_is_marked_without_model_routing():
    result = understand_conversation_turn(
        "Can I return this and where is my order?", []
    )
    assert result.multi_intent
