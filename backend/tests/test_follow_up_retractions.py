"""Follow-up safety: customer retractions must not be interpreted as approval."""
import pytest

from app.features.ai.application.follow_up import ACTION_RETRACTION


@pytest.mark.parametrize("message", [
    "don't cancel", "do not refund", "never return",
    "wait, don't cancel", "actually do not refund", "please don't return",
])
def test_retraction_detected(message):
    assert ACTION_RETRACTION.search(message)


@pytest.mark.parametrize("message", [
    "please cancel", "yes, refund it", "what is your return policy?",
])
def test_normal_message_not_retraction(message):
    assert ACTION_RETRACTION.search(message) is None
