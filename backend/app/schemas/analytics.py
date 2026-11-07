from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AIUsageDay(BaseModel):
    date: date
    executions: int
    prompt_tokens: int
    completion_tokens: int
    failed: int


class AIExecutionErrorCount(BaseModel):
    code: str
    count: int


class AIBotUsage(BaseModel):
    bot_id: UUID
    bot_name: str
    executions: int
    succeeded: int
    failed: int
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float | None
    average_latency_ms: int | None


class AIUsageOut(BaseModel):
    start_date: date
    end_date: date
    executions: int
    succeeded: int
    failed: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    daily: list[AIUsageDay]
    bots: list[AIBotUsage] = Field(default_factory=list)
    top_errors: list[AIExecutionErrorCount] = Field(default_factory=list)
    model_backed_responses: int = 0
    responses_with_document_citations: int = 0
    document_citation_rate: float | None = None


class IntegrationDeliveryDay(BaseModel):
    date: date
    total: int
    succeeded: int
    failed: int
    queued: int
    running: int
    cancelled: int


class IntegrationDeliveryProvider(BaseModel):
    provider_id: str
    total: int
    succeeded: int
    failed: int


class IntegrationDeliveryError(BaseModel):
    code: str
    count: int


class IntegrationDeliveryAnalyticsOut(BaseModel):
    start_date: date
    end_date: date
    total: int
    succeeded: int
    failed: int
    queued: int
    running: int
    cancelled: int
    average_attempts: float | None
    providers: list[IntegrationDeliveryProvider]
    daily: list[IntegrationDeliveryDay]
    top_errors: list[IntegrationDeliveryError]


class CommerceApprovalDay(BaseModel):
    date: date
    total: int
    pending: int
    approved: int
    rejected: int
    expired: int
    cancelled: int


class CommerceApprovalAnalyticsOut(BaseModel):
    start_date: date
    end_date: date
    total: int
    pending: int
    approved: int
    rejected: int
    expired: int
    cancelled: int
    execution_succeeded: int
    execution_failed: int
    average_review_seconds: float | None
    daily: list[CommerceApprovalDay]


class SupportResponseDay(BaseModel):
    date: date
    conversations: int
    responded: int
    average_first_response_seconds: float | None


class SupportResponseAnalyticsOut(BaseModel):
    start_date: date
    end_date: date
    conversations: int
    responded: int
    awaiting_first_response: int
    average_first_response_seconds: float | None
    median_first_response_seconds: float | None
    daily: list[SupportResponseDay]


class OperationalAlertOut(BaseModel):
    code: Literal[
        "background_jobs_overdue",
        "ai_execution_failed",
        "automation_execution_failed",
        "catalog_sync_failed",
        "catalog_webhook_failed",
        "outbound_delivery_failed",
        "document_ingestion_failed",
        "commerce_approval_pending",
        "commerce_execution_failed",
    ]
    severity: Literal["attention", "review"]
    title: str
    description: str
    count: int
    action_label: str
    href: str


class OperationalAlertsOut(BaseModel):
    generated_at: datetime
    window_start: datetime
    alerts: list[OperationalAlertOut]


class FailedBackgroundJobOut(BaseModel):
    job_id: UUID
    document_id: UUID | None = None
    correlation_id: str | None = None
    job_kind: Literal[
        "ai_execution",
        "automation_execution",
        "document_ingestion",
        "commerce_action",
        "catalog_sync",
        "catalog_webhook",
        "outbound_delivery",
    ]
    failed_at: datetime
    attempts: int
    error_code: str | None
    manual_retry_count: int = 0
    manual_retry_available: bool = False


class FailedBackgroundJobsOut(BaseModel):
    generated_at: datetime
    total_failed: int
    items: list[FailedBackgroundJobOut]


class JobTraceEventOut(BaseModel):
    job_id: UUID
    job_kind: Literal[
        "ai_execution",
        "automation_execution",
        "document_ingestion",
        "commerce_action",
        "catalog_sync",
        "catalog_webhook",
        "outbound_delivery",
    ]
    status: str
    created_at: datetime
    completed_at: datetime | None
    attempts: int
    max_attempts: int | None
    error_code: str | None


class JobTraceOut(BaseModel):
    correlation_id: str
    generated_at: datetime
    events: list[JobTraceEventOut]


class AIEvaluationCreate(BaseModel):
    execution_id: UUID
    rating: Literal["helpful", "not_helpful"]
    category: Literal["accuracy", "grounding", "relevance", "tone"] | None = None


class AIEvaluationOut(BaseModel):
    id: UUID
    execution_id: UUID
    rating: Literal["helpful", "not_helpful"]
    category: Literal["accuracy", "grounding", "relevance", "tone"] | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIEvaluationSummaryOut(BaseModel):
    start_date: date
    end_date: date
    rated: int
    helpful: int
    not_helpful: int
    helpful_rate: float | None
    by_category: dict[str, int] = Field(default_factory=dict)
