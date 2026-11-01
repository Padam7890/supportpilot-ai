from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.integrations.core import (
    CommerceCapability,
    IncomingMessage,
    IntegrationCapability,
    IntegrationError,
    IntegrationErrorCode,
    IntegrationRegistry,
    ProviderDescriptor,
)


class FakeCommerce:
    async def list_orders(self, connection, *, limit, cursor):
        return {"items": [], "next_cursor": cursor}

    async def lookup_order(self, connection, *, order_number, verified_customer_email):
        return None


class FakeProvider:
    descriptor = ProviderDescriptor(
        provider_id="test_shop",
        display_name="Test shop",
        version="1",
        capabilities=frozenset({IntegrationCapability.COMMERCE}),
    )

    def __init__(self, commerce=None):
        self.commerce = commerce or FakeCommerce()

    def get_capability(self, capability):
        if capability is IntegrationCapability.COMMERCE:
            return self.commerce
        return None


def test_registry_lists_real_registered_provider_and_resolves_capability():
    registry = IntegrationRegistry()
    provider = FakeProvider()
    registry.register(provider)

    assert registry.list_providers() == (provider.descriptor,)
    assert registry.get_provider("test_shop") is provider
    assert (
        registry.get_capability("test_shop", IntegrationCapability.COMMERCE, CommerceCapability)
        is provider.commerce
    )


def test_registry_rejects_duplicate_provider_ids():
    registry = IntegrationRegistry()
    registry.register(FakeProvider())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeProvider())


def test_registry_rejects_declared_but_missing_capabilities():
    registry = IntegrationRegistry()
    provider = FakeProvider(commerce=None)
    provider.commerce = None

    with pytest.raises(ValueError, match="declares missing capabilities"):
        registry.register(provider)


def test_registry_uses_safe_errors_for_unknown_provider_or_capability():
    registry = IntegrationRegistry()
    registry.register(FakeProvider())

    with pytest.raises(IntegrationError) as provider_error:
        registry.get_provider("missing")
    assert provider_error.value.code is IntegrationErrorCode.PROVIDER_NOT_FOUND
    assert provider_error.value.retryable is False

    with pytest.raises(IntegrationError) as capability_error:
        registry.get_capability("test_shop", IntegrationCapability.MESSAGING, CommerceCapability)
    assert capability_error.value.code is IntegrationErrorCode.UNSUPPORTED_CAPABILITY


def test_incoming_message_contract_is_strict_and_provider_scoped():
    event = IncomingMessage(
        organization_id=uuid4(),
        integration_connection_id=uuid4(),
        provider_id="test_shop",
        external_conversation_id="thread-1",
        external_message_id="message-1",
        external_sender_id="customer-9",
        content="Can you help?",
        occurred_at=datetime.now(UTC),
    )
    assert event.external_message_id == "message-1"
    with pytest.raises(ValueError):
        IncomingMessage.model_validate({**event.model_dump(), "untrusted_org_id": "other"})
