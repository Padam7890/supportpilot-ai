import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedOut


class TicketCreate(BaseModel):
    customer_id: uuid.UUID
    subject: str = Field(min_length=3, max_length=240)
    description: str | None = None
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")


class TicketUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=3, max_length=240)
    description: str | None = None
    status: str | None = Field(default=None, pattern=r"^(open|pending|resolved|closed)$")
    priority: str | None = Field(default=None, pattern=r"^(low|normal|high|urgent)$")
    assignee_id: uuid.UUID | None = None


class TicketOut(TimestampedOut):
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    assignee_id: uuid.UUID | None
    subject: str
    description: str | None
    status: str
    priority: str
    customer_name: str | None = None
    assignee_name: str | None = None


class TicketPage(BaseModel):
    items: list[TicketOut]
    total: int
    limit: int
    offset: int


class TicketActivityOut(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_name: str | None
    activity_type: str
    details: dict
    created_at: datetime


class TicketVolumeOut(BaseModel):
    date: date
    count: int


class TicketStatsOut(BaseModel):
    total_tickets: int
    open_tickets: int
    pending_tickets: int
    resolved_tickets: int
    closed_tickets: int
    by_status: dict[str, int]
    by_priority: dict[str, int]
    volume: list[TicketVolumeOut]
