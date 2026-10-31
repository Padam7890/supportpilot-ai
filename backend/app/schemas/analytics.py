from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AIUsageDay(BaseModel):
    date: date
    executions: int
    prompt_tokens: int
    completion_tokens: int


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
