import pytest
from pydantic import ValidationError

from app.api.routes.widgets import normalize_origin
from app.core.security import create_widget_visitor_token, decode_widget_visitor_token
from app.schemas.widget import (
    WidgetFirstMessage,
    WidgetOrderVerificationCode,
    WidgetOrderVerificationStart,
)
from app.services.ai_worker import _question_order_number
from app.services.widget_ai import (
    ACCOUNT_HELP_REPLY,
    CAPABILITIES_REPLY,
    GREETING_REPLY,
    HANDOFF_MESSAGE,
    ORDER_ACTION_REPLY,
    ORDER_VERIFICATION_MESSAGE,
    REFUND_ACTION_REPLY,
    THANKS_REPLY,
    widget_greeting_reply,
    widget_missing_knowledge_reply,
    widget_purchase_reply,
    widget_request_needs_human,
    widget_sensitive_reply,
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
    ("message", "expected"),
    [
        ("Thanks so much!", THANKS_REPLY),
        ("What can you do?", CAPABILITIES_REPLY),
    ],
)
def test_widget_ai_handles_simple_conversation_without_model_call(message, expected):
    assert widget_greeting_reply(message) == expected


@pytest.mark.parametrize(
    "message",
    ["hello, where is my order?", "hey can I get a refund?", "hello there! can you help with an order?"],
)
def test_widget_ai_does_not_treat_requests_as_standalone_greetings(message):
    assert widget_greeting_reply(message) is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Where is my order #1001?", ORDER_VERIFICATION_MESSAGE),
        ("Please cancel my order", ORDER_ACTION_REPLY),
        ("I want a refund", REFUND_ACTION_REPLY),
        ("Can you change my account address?", ACCOUNT_HELP_REPLY),
    ],
)
def test_widget_sensitive_requests_get_contextual_safe_next_steps(message, expected):
    result = widget_sensitive_reply(message)
    assert result is not None
    assert result[0] == expected


def test_widget_missing_knowledge_replies_are_specific_to_the_question_type():
    product = widget_missing_knowledge_reply("Is this product available in blue?")
    policy = widget_missing_knowledge_reply("What is your return policy?")
    general = widget_missing_knowledge_reply("Can you help me with something?")
    assert "Which item" in product
    assert "exact policy" in policy
    assert "more detail" in general
    assert len({product, policy, general}) == 3


@pytest.mark.parametrize(
    "message",
    [
        "I want to buy this",
        "Can I purchase the first one?",
        "I would like to order that product",
        "How do I place an order?",
        "Add it to my cart",
        "Checkout now",
    ],
)
def test_widget_purchase_requests_are_directed_to_store_checkout(message):
    reply = widget_purchase_reply(message)

    assert reply is not None
    assert "can’t place orders" in reply
    assert "product page" in reply
    assert "complete checkout there" in reply


@pytest.mark.parametrize(
    "message",
    ["Where is my order #1001?", "I want to cancel my order", "What is your order status?", "Hi"],
)
def test_widget_purchase_reply_does_not_capture_support_requests(message):
    assert widget_purchase_reply(message) is None


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is my order status?", None),
        ("Where is order #1004?", "1004"),
        ("Can you check order number 1004?", "1004"),
    ],
)
def test_verified_order_followups_only_select_an_explicit_order_number(question, expected):
    assert _question_order_number(question) == expected


def test_widget_order_verification_requires_order_email_and_six_digit_code():
    assert WidgetOrderVerificationStart(order_number="#1001", email="shopper@example.com", consent=True)
    assert WidgetOrderVerificationCode(code="042681").code == "042681"
    with pytest.raises(ValidationError):
        WidgetOrderVerificationCode(code="123")
