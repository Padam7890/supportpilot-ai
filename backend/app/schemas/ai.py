import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints


class AIPlaygroundRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=2000)]


class AIReplyDraftRequest(BaseModel):
    conversation_id: uuid.UUID
    instructions: Annotated[str | None, StringConstraints(strip_whitespace=True, max_length=500)] = None
    shopify_order_number: Annotated[str | None, StringConstraints(strip_whitespace=True, min_length=1, max_length=60, pattern=r"^#?[A-Za-z0-9-]+$")] = None


class AICitation(BaseModel):
    document_id: uuid.UUID
    document_name: str
    chunk_index: int
    excerpt: str


class AIExecutionOut(BaseModel):
    id: uuid.UUID
    kind: Literal["playground", "reply_draft", "widget_reply"]
    status: Literal["queued", "running", "succeeded", "failed"]
    delivery_mode: Literal["draft_only", "auto_reply"] | None = None
    reply_status: Literal["processing", "draft_ready", "sent", "escalated", "failed"] | None = None
    safe_summary: str | None
    draft: str | None
    citations: list[AICitation]
    tool_outcomes: list[dict[str, str | int]]
    usage: dict[str, int]
    model_name: str | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class AIExecutionPage(BaseModel):
    items: list[AIExecutionOut]
    total: int
    limit: int
    offset: int


class WidgetAIReplyStatusOut(BaseModel):
    status: Literal["processing", "draft_ready", "sent", "escalated", "failed"]
    delivery_mode: Literal["draft_only", "auto_reply"]
    draft: str | None
    safe_summary: str | None
    citations: list[AICitation]
    updated_at: datetime
