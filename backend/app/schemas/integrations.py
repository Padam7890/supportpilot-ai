from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class IntegrationProviderOut(BaseModel):
    provider_id: str
    display_name: str
    version: str
    capabilities: list[str]


class IntegrationConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ai_agent_id: UUID | None = None
    provider_id: str
    external_account_id: str
    display_name: str
    status: Literal["pending", "connected", "disconnected", "error", "reauthorization_required"]
    safe_configuration: dict[str, Any]
    connected_at: datetime | None
    last_checked_at: datetime | None
    last_error_code: str | None
    created_at: datetime
    updated_at: datetime


class IntegrationConnectionListOut(BaseModel):
    items: list[IntegrationConnectionOut]
    total: int


class IntegrationConnectionAuditOut(BaseModel):
    id: UUID
    event_type: Literal["connected", "reauthorized", "disconnected", "bot_routing_changed"]
    actor_name: str | None
    provider_id: str
    auth_mode: str | None
    granted_scopes: list[str]
    previous_ai_agent_id: UUID | None = None
    ai_agent_id: UUID | None = None
    created_at: datetime


class IntegrationConnectionRoutingUpdate(BaseModel):
    """Select an active tenant bot for new inbound conversations; null uses the default bot."""

    ai_agent_id: UUID | None


class IntegrationConnectionAuditPageOut(BaseModel):
    items: list[IntegrationConnectionAuditOut]
    total: int
    limit: int
    offset: int


class IntegrationConnectionEventOut(BaseModel):
    status: Literal["disconnected"]
    message: str


class IntegrationWebhookEventOut(BaseModel):
    id: UUID
    provider_id: str
    event_type: str
    occurred_at: datetime | None
    received_at: datetime
    processing_status: Literal["received", "queued", "running", "succeeded", "failed"]
    attempt_count: int
    last_error_code: str | None
    correlation_id: str | None = None
    manual_retry_count: int
    manual_retry_available: bool


class IntegrationWebhookRetryOut(BaseModel):
    id: UUID
    processing_status: Literal["queued"]
    manual_retry_count: int
    message: str


class IntegrationWebhookEventPageOut(BaseModel):
    items: list[IntegrationWebhookEventOut]
    total: int
    limit: int
    offset: int


class IntegrationDeliveryOut(BaseModel):
    id: UUID
    message_id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempt_count: int
    max_attempts: int
    manual_retry_count: int
    manual_retry_available: bool
    last_error_code: str | None
    correlation_id: str | None = None
    created_at: datetime
    completed_at: datetime | None


class IntegrationDeliveryPageOut(BaseModel):
    items: list[IntegrationDeliveryOut]
    total: int
    limit: int
    offset: int


class IntegrationDeliveryRetryOut(BaseModel):
    id: UUID
    status: Literal["queued"]
    manual_retry_count: int
    message: str


class ShopifyAccessAuditOut(BaseModel):
    id: UUID
    actor_name: str
    resource_type: str
    result_count: int
    outcome: str | None
    created_at: datetime


class ShopifyAccessAuditPageOut(BaseModel):
    items: list[ShopifyAccessAuditOut]
    total: int
    limit: int
    offset: int
