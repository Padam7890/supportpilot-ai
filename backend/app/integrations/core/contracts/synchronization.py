from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SyncResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    next_cursor: str | None = Field(default=None, max_length=2048)
    has_more: bool
    records_seen: int = Field(ge=0)
    completed_at: datetime
