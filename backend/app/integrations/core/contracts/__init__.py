from app.integrations.core.contracts.cart import CartLine, CartSnapshot
from app.integrations.core.contracts.catalog import (
    CatalogImage,
    CatalogPriceSnapshot,
    CatalogProductPage,
    CatalogProductSnapshot,
    CatalogVariantSnapshot,
)
from app.integrations.core.contracts.messaging import (
    DeliveryReceipt,
    IncomingMessage,
    MessageAttachment,
    OutboundMessage,
)
from app.integrations.core.contracts.provider import IntegrationConnectionRef, ProviderDescriptor
from app.integrations.core.contracts.synchronization import SyncResult
from app.integrations.core.contracts.webhooks import VerifiedWebhookEvent

__all__ = [
    "CartLine",
    "CartSnapshot",
    "CatalogImage",
    "CatalogPriceSnapshot",
    "CatalogProductPage",
    "CatalogProductSnapshot",
    "CatalogVariantSnapshot",
    "DeliveryReceipt",
    "IncomingMessage",
    "IntegrationConnectionRef",
    "MessageAttachment",
    "OutboundMessage",
    "ProviderDescriptor",
    "SyncResult",
    "VerifiedWebhookEvent",
]
