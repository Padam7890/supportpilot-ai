from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceAuditItem(BaseModel):
    id: UUID
    category: Literal["AI bot", "Knowledge", "Team", "Integration", "Commerce", "Ticket"]
    target_id: UUID
    event_type: str
    actor_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkspaceAuditPage(BaseModel):
    items: list[WorkspaceAuditItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)
