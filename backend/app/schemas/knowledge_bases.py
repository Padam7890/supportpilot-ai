from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class KnowledgeBaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class KnowledgeBaseUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class KnowledgeBaseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    description: str | None
    status: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class KnowledgeBaseListItem(KnowledgeBaseOut):
    document_count: int = Field(ge=0)
    ready_document_count: int = Field(ge=0)
    processing_document_count: int = Field(ge=0)
    failed_document_count: int = Field(ge=0)


class KnowledgeBasePage(BaseModel):
    items: list[KnowledgeBaseListItem]
    total: int
    limit: int
    offset: int


class KnowledgeBaseAuditOut(BaseModel):
    id: UUID
    knowledge_base_id: UUID
    actor_user_id: UUID
    actor_name: str
    event_type: str
    details: dict[str, object]
    created_at: datetime


class KnowledgeBaseAuditPage(BaseModel):
    items: list[KnowledgeBaseAuditOut]
    total: int
    limit: int
    offset: int
