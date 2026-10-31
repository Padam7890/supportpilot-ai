import uuid

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedOut


class ConversationCreate(BaseModel):
    channel: str = Field(default="web", pattern=r"^(web|email|chat|api)$")


class ConversationOut(TimestampedOut):
    organization_id: uuid.UUID
    ticket_id: uuid.UUID
    channel: str
    status: str


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    content_type: str = Field(default="text", pattern=r"^(text|html|markdown)$")


class MessageOut(TimestampedOut):
    organization_id: uuid.UUID
    conversation_id: uuid.UUID
    sender_type: str
    sender_user_id: uuid.UUID | None
    content: str
    content_type: str
    sender_name: str | None = None
