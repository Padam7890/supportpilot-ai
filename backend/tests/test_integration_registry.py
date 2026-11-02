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
    OutboundMessagingCapability,
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


def test_shopify_provider_registers_only_catalog_and_verified_webhook_capabilities():
    from app.integrations.providers.shopify.provider import ShopifyCatalogProvider

    provider = ShopifyCatalogProvider(lambda connection: None)
    assert provider.descriptor.capabilities == frozenset(
        {IntegrationCapability.PRODUCT_CATALOG, IntegrationCapability.WEBHOOKS}
    )
    assert provider.get_capability(IntegrationCapability.WEBHOOKS) is not None
    assert provider.get_capability(IntegrationCapability.MESSAGING) is None


def test_shopify_webhook_adapter_verifies_then_normalizes_minimal_product_event(monkeypatch):
    from app.integrations.providers.shopify.webhooks import ShopifyWebhookAdapter

    monkeypatch.setattr(
        "app.integrations.providers.shopify.webhooks.verify_webhook_hmac",
        lambda raw, signature: signature == "verified",
    )
    event = ShopifyWebhookAdapter().verify_and_normalize(
        headers={
            "X-Shopify-Hmac-Sha256": "verified",
            "X-Shopify-Topic": "products/update",
            "X-Shopify-Webhook-Id": "event-1",
            "X-Shopify-Shop-Domain": "sample.myshopify.com",
        },
        raw_body=b'{"id": "42", "title": "not retained"}',
    )
    assert event.external_account_id == "sample.myshopify.com"
    assert event.deduplication_key == "shopify:event-1"
    assert event.normalized_payload == {
        "external_product_id": "gid://shopify/Product/42",
        "shop_domain": "sample.myshopify.com",
    }


def test_shopify_webhook_adapter_rejects_invalid_signature(monkeypatch):
    from app.integrations.providers.shopify.webhooks import ShopifyWebhookAdapter

    monkeypatch.setattr(
        "app.integrations.providers.shopify.webhooks.verify_webhook_hmac",
        lambda raw, signature: False,
    )
    with pytest.raises(IntegrationError) as error:
        ShopifyWebhookAdapter().verify_and_normalize(headers={}, raw_body=b"{}")
    assert error.value.code is IntegrationErrorCode.PERMISSION_DENIED
    assert error.value.retryable is False


def test_messaging_capability_is_explicit_and_provider_neutral():
    class FakeOutbound:
        async def send_message(self, connection, *, external_conversation_id, message, idempotency_key):
            raise NotImplementedError

    assert isinstance(FakeOutbound(), OutboundMessagingCapability)
