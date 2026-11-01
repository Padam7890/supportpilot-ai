import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import TimestampedOut


class ConversationCreate(BaseModel):
    channel: str = Field(default="web", pattern=r"^(web|email|chat|api)$")


class ShoppingContextOut(BaseModel):
    model_config = ConfigDict(extra="ignore")

    active: bool = False
    intent: dict[str, object] = Field(default_factory=dict)
    required_constraints: list[str] = Field(default_factory=list)
    soft_preferences: dict[str, int] = Field(default_factory=dict)
    rejected_product_ids: list[uuid.UUID] = Field(default_factory=list)
    last_displayed_recommendations: list[dict[str, object]] = Field(default_factory=list)
    selected_products_for_comparison: list[dict[str, uuid.UUID]] = Field(default_factory=list)
    clarification_state: str | None = None
    rejected_recommendation_count: int = 0
    unsupported_request_count: int = 0
    handoff_offer_pending: bool = False


class ConversationOut(TimestampedOut):
    organization_id: uuid.UUID
    ticket_id: uuid.UUID
    channel: str
    status: str
    ai_mode: Literal["ai", "human"]
    shopping_context: ShoppingContextOut | None = None


class ConversationAIModeUpdate(BaseModel):
    mode: Literal["ai", "human"]


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    content_type: str = Field(default="text", pattern=r"^(text|html|markdown)$")


class InternalNoteCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(min_length=1, max_length=20000)


class MessageOut(TimestampedOut):
    organization_id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: str
    sender_user_id: uuid.UUID | None
    content: str
    content_type: str
    sender_name: str | None = None


class InboxCustomerOut(BaseModel):
    id: uuid.UUID
    name: str
    email: str | None


class InboxAssigneeOut(BaseModel):
    id: uuid.UUID
    name: str


class InboxLatestMessageOut(BaseModel):
    preview: str
    created_at: datetime
    sender_type: str


class InboxItemOut(BaseModel):
    ticket_id: uuid.UUID
    conversation_id: uuid.UUID | None
    subject: str
    status: Literal["open", "pending", "resolved", "closed"]
    priority: Literal["low", "normal", "high", "urgent"]
    customer: InboxCustomerOut
    assignee: InboxAssigneeOut | None
    latest_message: InboxLatestMessageOut | None
    unread_count: int
    updated_at: datetime


class InboxPage(BaseModel):
    items: list[InboxItemOut]
    limit: int
    next_cursor: str | None


class ConversationReadOut(BaseModel):
    conversation_id: uuid.UUID
    last_read_at: datetime | None
    last_read_message_id: uuid.UUID | None
