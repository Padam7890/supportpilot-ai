import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class IngestionJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    correlation_id: str | None = None
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    last_error: str | None
    requires_replacement: bool = False
    created_at: datetime


class KnowledgeDocumentOut(BaseModel):
    id: uuid.UUID
    knowledge_base_id: uuid.UUID
    name: str
    content_type: str
    size_bytes: int
    status: Literal["queued", "processing", "ready", "failed"]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    jobs: list[IngestionJobOut]


class KnowledgeSourcePreviewOut(BaseModel):
    content: str
    truncated: bool
    max_bytes: int


class KnowledgeDocumentPage(BaseModel):
    items: list[KnowledgeDocumentOut]
    total: int
    limit: int
    offset: int


class KnowledgeDocumentMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_base_id: uuid.UUID


class KnowledgeSearchResult(BaseModel):
    document_id: uuid.UUID
    document_name: str
    knowledge_base_name: str
    chunk_index: int
    excerpt: str


class KnowledgeSearchPage(BaseModel):
    items: list[KnowledgeSearchResult]
    total: int
    limit: int
    offset: int
