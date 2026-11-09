import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints


class AIPlaygroundTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]


class AIPlaygroundRequest(BaseModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
    ]
    ai_agent_id: uuid.UUID | None = None
    conversation_history: list[AIPlaygroundTurn] = Field(default_factory=list, max_length=6)


class AIReplyDraftRequest(BaseModel):
    conversation_id: uuid.UUID
    instructions: Annotated[
        str | None, StringConstraints(strip_whitespace=True, max_length=500)
    ] = None
    shopify_order_number: Annotated[
        str | None,
        StringConstraints(
            strip_whitespace=True, min_length=1, max_length=60, pattern=r"^#?[A-Za-z0-9-]+$"
        ),
    ] = None


class AICitation(BaseModel):
    document_id: uuid.UUID
    document_name: str
    knowledge_base_name: str | None = None
    chunk_index: int
    excerpt: str
    match_basis: Literal["chunk_content", "source_title", "semantic", "hybrid"] | None = None
    rrf_score: float | None = None
    semantic_similarity: float | None = None
    keyword_rank: int | None = None
    semantic_rank: int | None = None


class AIPlaygroundRetrievalPreviewRequest(BaseModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=4, max_length=2000)
    ]
    ai_agent_id: uuid.UUID | None = None
    conversation_history: list[AIPlaygroundTurn] = Field(default_factory=list, max_length=6)


class AIPlaygroundRetrievalPreviewOut(BaseModel):
    ai_agent_id: uuid.UUID
    ai_agent_name: str
    status: Literal[
        "matched", "no_matches", "no_assigned_bases", "no_ready_documents", "query_too_broad"
    ]
    active_assigned_base_count: int
    ready_document_count: int
    matched_passage_count: int
    retrieval_method: Literal["keyword", "semantic", "hybrid", "none"] = "none"
    retrieval_latency_ms: int = 0
    embedding_status: str = "disabled"
    embedding_coverage: float | None = None
    retrieval_outcome: str = "ok"
    keyword_candidate_count: int = 0
    semantic_candidate_count: int = 0
    retrieval_terms: list[Annotated[str, StringConstraints(max_length=80)]] = Field(
        default_factory=list,
        max_length=64,
    )
    sources: list[AICitation]


class AIExecutionOut(BaseModel):
    id: uuid.UUID
    ai_agent_id: uuid.UUID | None = None
    ai_agent_config_version: int
    kind: Literal["playground", "reply_draft", "widget_reply", "recommendation"]
    status: Literal["queued", "running", "succeeded", "failed"]
    correlation_id: str | None = None
    delivery_mode: Literal["draft_only", "auto_reply"] | None = None
    reply_status: Literal["processing", "draft_ready", "sent", "escalated", "failed"] | None = None
    safe_summary: str | None
    draft: str | None
    recommendation_result: dict[str, Any] | None = None
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


class AIExecutionRetryOut(BaseModel):
    id: uuid.UUID
    status: Literal["queued"]
    manual_retry_count: int
    message: str


class WidgetAIReplyStatusOut(BaseModel):
    status: Literal["processing", "draft_ready", "sent", "escalated", "failed"]
    delivery_mode: Literal["draft_only", "auto_reply"]
    ai_agent_name: str
    correlation_id: str | None = None
    draft: str | None
    safe_summary: str | None
    citations: list[AICitation]
    updated_at: datetime
