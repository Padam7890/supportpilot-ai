from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VerifiedWebhookEvent(BaseModel):
    """Safe normalized webhook fields; raw bodies belong in protected storage."""

    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=2, max_length=48)
    external_account_id: str = Field(min_length=1, max_length=512)
    external_event_id: str = Field(min_length=1, max_length=512)
    event_type: str = Field(min_length=1, max_length=120)
    occurred_at: datetime | None = None
    deduplication_key: str = Field(min_length=1, max_length=512)
    normalized_payload: dict[str, Any] = Field(default_factory=dict)
