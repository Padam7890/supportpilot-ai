import pytest
from pydantic import ValidationError

from app.api.routes.widgets import normalize_origin
from app.core.security import create_widget_visitor_token, decode_widget_visitor_token
from app.schemas.widget import WidgetFirstMessage
from app.services.widget_ai import (
    GREETING_REPLY,
    HANDOFF_MESSAGE,
    widget_greeting_reply,
    widget_request_needs_human,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://Store.Example/", "https://store.example"),
        ("https://demo.myshopify.com", "https://demo.myshopify.com"),
        ("http://localhost:3000", "http://localhost:3000"),
    ],
)
def test_widget_origin_normalization(value, expected):
    assert normalize_origin(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://store.example/path",
        "https://user:password@store.example",
        "http://store.example",
        "file:///tmp/store.html",
    ],
)
def test_widget_origin_rejects_non_origins(value):
    with pytest.raises(ValueError):
        normalize_origin(value)


def test_widget_first_message_requires_explicit_consent_for_contact_details():
    with pytest.raises(ValidationError):
        WidgetFirstMessage(content="Where is my package?", visitor_email="shopper@example.com")
    accepted = WidgetFirstMessage(
        content="  Where is my package?  ", visitor_email="shopper@example.com", contact_consent=True
    )
    assert accepted.content == "Where is my package?"
    assert accepted.contact_consent is True


def test_widget_visitor_token_is_separate_and_scoped_to_one_conversation(monkeypatch):
    from datetime import UTC, datetime, timedelta

    from app.core.config import settings

    monkeypatch.setattr(settings, "jwt_secret", "widget-unit-test-secret-at-least-32-chars")
    token = create_widget_visitor_token(
        organization_id="00000000-0000-0000-0000-000000000001",
        widget_public_id="public-widget-id-123456789012",
        conversation_id="00000000-0000-0000-0000-000000000002",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    claims = decode_widget_visitor_token(token)
    assert claims["typ"] == "widget_visitor"
    assert claims["sub"] == "00000000-0000-0000-0000-000000000002"
    assert claims["org"] == "00000000-0000-0000-0000-000000000001"
    assert claims["wid"] == "public-widget-id-123456789012"


@pytest.mark.parametrize(
    "message",
    [
        "Where is my order #1001?",
        "Can I cancel this?",
        "I want a refund",
        "Please change my shipping address",
        "What payment did you charge?",
    ],
)
def test_widget_ai_hands_private_or_sensitive_requests_to_a_teammate(message):
    assert widget_request_needs_human(message)
    assert HANDOFF_MESSAGE


@pytest.mark.parametrize(
    "message",
    ["What are your delivery charges?", "Do you have weekend support?"],
)
def test_widget_ai_allows_faqs_to_use_tenant_knowledge(message):
    assert not widget_request_needs_human(message)


@pytest.mark.parametrize("message", ["hi", "Hello!", "hey there", "good morning"])
def test_widget_ai_handles_standalone_greetings_without_knowledge(message):
    assert widget_greeting_reply(message) == GREETING_REPLY


@pytest.mark.parametrize(
    "message",
    ["hello, where is my order?", "hey can I get a refund?", "hello there! can you help with an order?"],
)
def test_widget_ai_does_not_treat_requests_as_standalone_greetings(message):
    assert widget_greeting_reply(message) is None
