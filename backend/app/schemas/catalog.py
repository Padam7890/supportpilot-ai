from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CatalogVariantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    external_variant_id: str
    title: str
    sku: str | None
    attributes: dict[str, str]
    price: Decimal
    compare_at_price: Decimal | None
    currency: str
    availability: Literal["available", "unavailable", "unknown"]
    inventory_quantity: int | None
    synced_at: datetime


class CatalogProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    description: str | None
    brand: str | None
    category: str | None
    images: list[dict[str, str | None]]
    canonical_url: str | None
    status: Literal["active", "draft", "archived", "unknown"]
    specifications: dict[str, Any]
    synced_at: datetime
    variants: list[CatalogVariantOut]


class CatalogProductPageOut(BaseModel):
    items: list[CatalogProductOut]
    total: int
    limit: int
    offset: int


class CatalogStatusOut(BaseModel):
    connected: bool
    product_scope_granted: bool
    product_count: int
    last_sync_at: datetime | None
    last_error_code: str | None


class CatalogSyncJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mode: Literal["full", "incremental", "reconcile"]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    correlation_id: str | None = None
    attempt_count: int
    max_attempts: int
    manual_retry_count: int = 0
    manual_retry_available: bool = False
    records_seen: int
    last_error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class CatalogSyncJobPageOut(BaseModel):
    items: list[CatalogSyncJobOut]
    total: int
    limit: int
    offset: int


class CatalogSyncRequest(BaseModel):
    mode: Literal["full", "incremental"] = "full"


class CatalogWebhookAccepted(BaseModel):
    accepted: bool = True
    duplicate: bool = False


class ShopifyProductWebhook(BaseModel):
    id: int | str
    title: str | None = Field(default=None, max_length=500)
    updated_at: datetime | None = None
