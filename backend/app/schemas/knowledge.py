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


class DocumentEmbeddingDiagnosticsOut(BaseModel):
    chunk_count: int
    embedded_chunk_count: int
    coverage: float | None = None
    latest_job_status: str | None = None
    latest_job_error_code: str | None = None
    embedding_model: str | None = None
    embedding_version: str | None = None


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
    embedding: DocumentEmbeddingDiagnosticsOut | None = None


class KnowledgeSourcePreviewOut(BaseModel):
    content: str
    truncated: bool
    max_bytes: int


class KnowledgeDocumentPage(BaseModel):
    items: list[KnowledgeDocumentOut]
    total: int
    limit: int
    offset: int


class DocumentEmbeddingJobOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    embedding_model: str
    embedding_version: str
    dimensions: int
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    last_error_code: str | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentEmbeddingBackfillOut(BaseModel):
    queued_count: int
    job_ids: list[uuid.UUID]
    embedding_model: str
    embedding_version: str


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
