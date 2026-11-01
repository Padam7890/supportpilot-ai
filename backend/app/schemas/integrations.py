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


class IntegrationConnectionEventOut(BaseModel):
    status: Literal["disconnected"]
    message: str
