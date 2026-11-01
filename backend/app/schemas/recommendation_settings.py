from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RecommendationSettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    mode: Literal["automatic", "explicit"] = "automatic"
    max_products: int = Field(default=3, ge=1, le=5)
    in_stock_only: bool = False
    excluded_product_ids: list[UUID] = Field(default_factory=list, max_length=500)
    excluded_collection_ids: list[str] = Field(default_factory=list, max_length=100)
    comparison_enabled: bool = True
    upselling_enabled: bool = False
    cross_selling_enabled: bool = False
    ranking_preferences: dict[str, int] = Field(default_factory=dict)
    human_handoff_preferences: dict[str, int | bool] = Field(default_factory=lambda: {"enabled": True, "rejected_threshold": 3, "unsupported_threshold": 2})

    @field_validator("excluded_collection_ids")
    @classmethod
    def valid_collection_ids(cls, value: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(item.strip() for item in value))
        if any(not item or len(item) > 200 for item in cleaned):
            raise ValueError("Collection identifiers must be 1–200 characters")
        return cleaned

    @field_validator("ranking_preferences")
    @classmethod
    def valid_weights(cls, value: dict[str, int]) -> dict[str, int]:
        allowed = {"feature_match", "use_case", "brand", "budget_fit", "reviews"}
        if set(value) - allowed or any(not 0 <= weight <= 100 for weight in value.values()):
            raise ValueError("Ranking weights must use supported keys and values from 0 to 100")
        return value

    @field_validator("human_handoff_preferences")
    @classmethod
    def valid_handoff(cls, value: dict[str, int | bool]) -> dict[str, int | bool]:
        if set(value) - {"enabled", "rejected_threshold", "unsupported_threshold"}:
            raise ValueError("Unsupported human handoff preference")
        for key in ("rejected_threshold", "unsupported_threshold"):
            if key in value and (isinstance(value[key], bool) or not 1 <= int(value[key]) <= 10):
                raise ValueError("Handoff thresholds must be between 1 and 10")
        if "enabled" in value and not isinstance(value["enabled"], bool):
            raise ValueError("Handoff enabled must be a boolean")
        return value


class RecommendationSettingsOut(RecommendationSettingsIn):
    id: UUID
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class RecommendationEventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: UUID
    message_id: UUID
    event_type: Literal["impression", "product_click", "comparison", "rejection"]
    product_id: UUID | None = None
    variant_id: UUID | None = None


class RecommendationEventOut(BaseModel):
    accepted: bool = True


class RecommendationTrendPoint(BaseModel):
    date: str
    impressions: int
    clicks: int
    comparisons: int
    no_results: int
    handoffs: int


class RecommendationAnalyticsOut(BaseModel):
    start_date: str
    end_date: str
    impressions: int
    product_clicks: int
    comparisons: int
    add_to_cart: int | None
    attributed_purchases: int | None
    direct_purchases: int | None
    assisted_purchases: int | None
    rejected_recommendations: int
    no_result_searches: int
    human_handoffs: int
    average_latency_ms: int | None
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float | None
    failed_executions: int
    error_codes: list[dict[str, str | int]] = Field(default_factory=list)
    attribution_window_days: int = 7
    conversion_tracking_available: bool = False
    trends: list[RecommendationTrendPoint] = Field(default_factory=list)
    top_recommended_products: list[dict[str, str | int]] = Field(default_factory=list)
    top_clicked_products: list[dict[str, str | int]] = Field(default_factory=list)
    no_result_categories: list[dict[str, str | int]] = Field(default_factory=list)
