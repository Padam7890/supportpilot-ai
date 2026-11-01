from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from app.integrations.core.contracts.cart import CartLine, CartSnapshot
from app.integrations.core.contracts.catalog import (
    CatalogPriceSnapshot,
    CatalogProductPage,
    CatalogProductSnapshot,
    CatalogVariantSnapshot,
)
from app.integrations.core.contracts.messaging import DeliveryReceipt, OutboundMessage
from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.core.contracts.synchronization import SyncResult
from app.integrations.core.contracts.webhooks import VerifiedWebhookEvent


@runtime_checkable
class MessagingCapability(Protocol):
    async def send_message(
        self,
        connection: IntegrationConnectionRef,
        *,
        external_conversation_id: str,
        message: OutboundMessage,
        idempotency_key: str,
    ) -> DeliveryReceipt: ...


@runtime_checkable
class CommerceCapability(Protocol):
    async def list_orders(
        self,
        connection: IntegrationConnectionRef,
        *,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]: ...

    async def lookup_order(
        self,
        connection: IntegrationConnectionRef,
        *,
        order_number: str,
        verified_customer_email: str,
    ) -> dict[str, Any] | None: ...


@runtime_checkable
class ProductCatalogCapability(Protocol):
    """Read and synchronize provider catalog data; independent of cart support."""

    async def list_products(
        self,
        connection: IntegrationConnectionRef,
        *,
        limit: int,
        cursor: str | None,
        updated_after: datetime | None = None,
    ) -> CatalogProductPage: ...

    async def get_product(
        self,
        connection: IntegrationConnectionRef,
        *,
        external_product_id: str,
    ) -> CatalogProductSnapshot | None: ...

    async def get_variant(
        self,
        connection: IntegrationConnectionRef,
        *,
        external_variant_id: str,
    ) -> CatalogVariantSnapshot | None: ...

    async def get_current_price(
        self,
        connection: IntegrationConnectionRef,
        *,
        external_variant_id: str,
    ) -> CatalogPriceSnapshot | None: ...

    async def search_products(
        self,
        connection: IntegrationConnectionRef,
        *,
        query: str,
        limit: int,
        cursor: str | None = None,
    ) -> CatalogProductPage: ...


@runtime_checkable
class CartCapability(Protocol):
    async def create_cart(
        self,
        connection: IntegrationConnectionRef,
        *,
        lines: list[CartLine],
        idempotency_key: str,
    ) -> CartSnapshot: ...


@runtime_checkable
class CheckoutCapability(Protocol):
    async def get_checkout_url(
        self,
        connection: IntegrationConnectionRef,
        *,
        external_cart_id: str,
    ) -> str | None: ...


@runtime_checkable
class WebhookCapability(Protocol):
    def verify_and_normalize(
        self,
        *,
        headers: dict[str, str],
        raw_body: bytes,
    ) -> VerifiedWebhookEvent: ...


@runtime_checkable
class SynchronizationCapability(Protocol):
    async def initial_sync(
        self,
        connection: IntegrationConnectionRef,
        *,
        cursor: str | None,
        limit: int,
    ) -> SyncResult: ...

    async def incremental_sync(
        self,
        connection: IntegrationConnectionRef,
        *,
        cursor: str | None,
        limit: int,
    ) -> SyncResult: ...
