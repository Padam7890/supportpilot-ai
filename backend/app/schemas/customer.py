import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import TimestampedOut


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    external_reference: str | None = Field(default=None, max_length=120)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    external_reference: str | None = Field(default=None, max_length=120)


class CustomerOut(TimestampedOut):
    organization_id: uuid.UUID
    name: str
    # Stored emails include synthetic addresses from widget/integration flows
    # (e.g. *@widget.invalid). Pydantic EmailStr rejects those TLDs, which broke
    # list/get responses with ResponseValidationError → 500.
    email: str = Field(min_length=1, max_length=320)
    phone: str | None
    external_reference: str | None


class CustomerPage(BaseModel):
    items: list[CustomerOut]
    total: int
    limit: int
    offset: int


class CustomerMessageHistoryItem(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    ticket_subject: str
    conversation_id: uuid.UUID
    sender_type: str
    sender_name: str | None
    content: str
    created_at: datetime


class CustomerMessageHistoryPage(BaseModel):
    items: list[CustomerMessageHistoryItem]
    total: int
    limit: int
    offset: int
