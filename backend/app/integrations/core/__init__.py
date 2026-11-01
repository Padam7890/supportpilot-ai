"""Stable public exports for integration contracts and registry."""

from app.integrations.core.contracts import (
    CartLine,
    CartSnapshot,
    CatalogImage,
    CatalogPriceSnapshot,
    CatalogProductPage,
    CatalogProductSnapshot,
    CatalogVariantSnapshot,
    DeliveryReceipt,
    IncomingMessage,
    IntegrationConnectionRef,
    MessageAttachment,
    OutboundMessage,
    ProviderDescriptor,
    SyncResult,
    VerifiedWebhookEvent,
)
from app.integrations.core.errors import IntegrationError, IntegrationErrorCode
from app.integrations.core.interfaces import (
    CartCapability,
    CheckoutCapability,
    CommerceCapability,
    IntegrationProvider,
    MessagingCapability,
    ProductCatalogCapability,
    SynchronizationCapability,
    WebhookCapability,
)
from app.integrations.core.registry import IntegrationRegistry
from app.integrations.core.types import IntegrationCapability

__all__ = [
    "CartCapability",
    "CartLine",
    "CartSnapshot",
    "CatalogImage",
    "CatalogPriceSnapshot",
    "CatalogProductPage",
    "CatalogProductSnapshot",
    "CatalogVariantSnapshot",
    "CheckoutCapability",
    "CommerceCapability",
    "DeliveryReceipt",
    "IncomingMessage",
    "IntegrationCapability",
    "IntegrationConnectionRef",
    "IntegrationError",
    "IntegrationErrorCode",
    "IntegrationProvider",
    "IntegrationRegistry",
    "MessageAttachment",
    "MessagingCapability",
    "OutboundMessage",
    "ProductCatalogCapability",
    "ProviderDescriptor",
    "SyncResult",
    "SynchronizationCapability",
    "VerifiedWebhookEvent",
    "WebhookCapability",
]
