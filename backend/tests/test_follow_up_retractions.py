"""Customer retractions must not be interpreted as approval."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.features.ai.application.follow_up import assess_widget_follow_up
from app.features.ai.application.policy_follow_up import FollowUpInterpretation


@pytest.mark.parametrize("message", [
    "don't cancel", "do not refund", "never return",
    "wait, don't cancel", "actually do not refund", "please don't return",
])
def test_retraction_detected(message):
    decision, _ = assess_widget_follow_up(
        message, [], agent_id=uuid4(), source_message_id=None, now=datetime.now(UTC),
        interpretation=FollowUpInterpretation(
            relation="new_topic", goal="none", confirmation="retract",
            action_target="order", confidence=0.99,
        ),
    )
    assert decision is not None and decision.decision == "declined"
    assert decision.review is None and decision.routed_question is None


@pytest.mark.parametrize("message", [
    "please cancel", "yes, refund it", "what is your return policy?",
])
def test_normal_message_not_retraction(message):
    decision, _ = assess_widget_follow_up(
        message, [], agent_id=uuid4(), source_message_id=None, now=datetime.now(UTC),
    )
    assert decision is None or decision.decision != "declined"
