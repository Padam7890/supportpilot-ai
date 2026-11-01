from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class MessageAttachment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=0, le=100 * 1024 * 1024)
    url: HttpUrl | None = None
    provider_file_id: str | None = Field(default=None, max_length=512)


class IncomingMessage(BaseModel):
    """Message normalized after a verified provider event or trusted widget call."""

    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    integration_connection_id: UUID | None = None
    provider_id: str = Field(min_length=2, max_length=48)
    external_conversation_id: str = Field(min_length=1, max_length=512)
    external_message_id: str = Field(min_length=1, max_length=512)
    external_sender_id: str = Field(min_length=1, max_length=512)
    sender_display_name: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=100_000)
    content_type: str = Field(default="text", min_length=1, max_length=40)
    attachments: list[MessageAttachment] = Field(default_factory=list, max_length=20)
    occurred_at: datetime
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class OutboundMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=100_000)
    content_type: str = Field(default="text", min_length=1, max_length=40)
    attachments: list[MessageAttachment] = Field(default_factory=list, max_length=20)


class DeliveryReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_message_id: str | None = Field(default=None, max_length=512)
    status: str = Field(pattern=r"^(accepted|sent|delivered|failed|unknown)$")
    accepted_at: datetime
    provider_status: str | None = Field(default=None, max_length=100)
