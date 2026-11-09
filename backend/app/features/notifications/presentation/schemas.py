from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    event_type: str
    category: str
    priority: str
    title: str
    body: str | None
    resource_type: str | None
    resource_id: UUID | None
    action_url: str | None
    created_at: datetime
    read_at: datetime | None


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    next_cursor: str | None
    has_more: bool


class NotificationUnreadCountResponse(BaseModel):
    unread_count: int


class NotificationPreferenceResponse(BaseModel):
    event_type: str
    in_app_enabled: bool
    email_enabled: bool


class NotificationPreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    in_app_enabled: bool | None = None
    email_enabled: bool | None = None


class ReadAllResponse(BaseModel):
    affected_count: int


class NotificationQuery(BaseModel):
    limit: int = Field(default=30, ge=1, le=100)
