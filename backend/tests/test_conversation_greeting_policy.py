"""Default pilot output guard regression cases."""

import pytest

from app.features.ai.application.conversation_greeting_policy import safe_first_contact_greeting


@pytest.mark.parametrize("message", [
    "Hello! How can I help you?",
    "Hi there, what can I help with today?",
])
def test_normal_greeting_allowed(message: str) -> None:
    assert safe_first_contact_greeting(message)


@pytest.mark.parametrize("message", [
    "We have 50 products available.",
    "Your order is on its way.",
    "We offer free shipping.",
    "Refunds take a week.",
    "Visit https://example.com",
    "Email support@example.com",
    "",
])
def test_unsupported_store_assertions_blocked(message: str) -> None:
    assert not safe_first_contact_greeting(message)
