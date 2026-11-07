import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import TimestampedOut


class TicketCreate(BaseModel):
    customer_id: uuid.UUID
    team_id: uuid.UUID | None = None
    subject: str = Field(min_length=3, max_length=240)
    description: str | None = None
    priority: str = Field(default="normal", pattern=r"^(low|normal|high|urgent)$")


class TicketUpdate(BaseModel):
    subject: str | None = Field(default=None, min_length=3, max_length=240)
    description: str | None = None
    status: str | None = Field(default=None, pattern=r"^(open|pending|resolved|closed)$")
    priority: str | None = Field(default=None, pattern=r"^(low|normal|high|urgent)$")
    assignee_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None


class TicketBulkUpdate(BaseModel):
    ticket_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    status: str | None = Field(default=None, pattern=r"^(open|pending|resolved|closed)$")
    priority: str | None = Field(default=None, pattern=r"^(low|normal|high|urgent)$")
    assignee_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        if len(set(self.ticket_ids)) != len(self.ticket_ids):
            raise ValueError("ticket_ids must be unique")
        changed_fields = self.model_fields_set.intersection({"status", "priority", "assignee_id", "team_id"})
        if not changed_fields:
            raise ValueError("At least one ticket field must be changed")
        if "status" in changed_fields and self.status is None:
            raise ValueError("status cannot be null")
        if "priority" in changed_fields and self.priority is None:
            raise ValueError("priority cannot be null")
        return self


class TicketBulkUpdateOut(BaseModel):
    updated_count: int
    changed_count: int
    ticket_ids: list[uuid.UUID]


class TicketLinkCreate(BaseModel):
    related_ticket_id: uuid.UUID


class TicketLinkOut(BaseModel):
    id: uuid.UUID
    related_ticket_id: uuid.UUID
    related_ticket_subject: str
    related_ticket_status: str
    related_ticket_priority: str
    created_by_user_id: uuid.UUID
    created_at: datetime


class TicketLinkPage(BaseModel):
    items: list[TicketLinkOut]
    total: int
    limit: int
    offset: int


class TicketOut(TimestampedOut):
    organization_id: uuid.UUID
    customer_id: uuid.UUID
    assignee_id: uuid.UUID | None
    team_id: uuid.UUID | None = None
    subject: str
    description: str | None
    status: str
    priority: str
    customer_name: str | None = None
    assignee_name: str | None = None
    team_name: str | None = None


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
