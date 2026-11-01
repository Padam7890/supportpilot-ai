"""Validated contracts for catalog recommendation requests and results."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, StringConstraints


class RecommendationRequest(BaseModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=2000)]


class RecommendationIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_recommendation: bool = True
    category: str | None = Field(default=None, max_length=120)
    budget_amount: Decimal | None = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    budget_currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    budget_strict: bool = True
    preferred_brand: str | None = Field(default=None, max_length=120)
    required_brand: str | None = Field(default=None, max_length=120)
    excluded_brands: list[str] = Field(default_factory=list, max_length=10)
    required_features: list[str] = Field(default_factory=list, max_length=12)
    optional_preferences: list[str] = Field(default_factory=list, max_length=12)
    use_case: str | None = Field(default=None, max_length=200)
    sort_by: Literal["relevance", "price_asc", "price_desc"] = "relevance"
    result_count: int = Field(default=3, ge=1, le=5)


class AppliedCriteria(BaseModel):
    category: str | None = None
    budget_amount: Decimal | None = None
    budget_currency: str | None = None
    budget_strict: bool
    preferred_brand: str | None = None
    required_brand: str | None = None
    excluded_brands: list[str] = Field(default_factory=list)
    required_features: list[str] = Field(default_factory=list)
    optional_preferences: list[str] = Field(default_factory=list)
    use_case: str | None = None
    sort_by: Literal["relevance", "price_asc", "price_desc"]


class RecommendationVariantOption(BaseModel):
    variant_id: UUID
    variant_title: str
    price: Decimal
    currency: str
    availability: Literal["available", "unavailable", "unknown"]
    verified_attributes: dict[str, str] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list, max_length=5)
    limitations: list[str] = Field(default_factory=list, max_length=12)


class RecommendedProduct(BaseModel):
    product_id: UUID
    variant_id: UUID
    title: str
    variant_title: str
    brand: str | None
    category: str | None
    price: Decimal
    currency: str
    availability: Literal["available", "unavailable", "unknown"]
    verified_attributes: dict[str, str] = Field(default_factory=dict)
    variant_options: list["RecommendationVariantOption"] = Field(default_factory=list, max_length=25)
    image_url: str | None
    product_url: str | None
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    limitations: list[str] = Field(default_factory=list)
    budget_overage: Decimal | None = None


class RecommendationResult(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    response_type: Literal["recommendations", "clarification", "unsupported", "no_match"]
    explanation: str
    applied_criteria: AppliedCriteria | None = None
    products: list[RecommendedProduct] = Field(default_factory=list, max_length=5)
    limitations: list[str] = Field(default_factory=list)
    available_actions: list[Literal["refine_search", "view_product"]] = Field(default_factory=list)
    suggested_follow_ups: list[str] = Field(default_factory=list, max_length=5)


class ComparedProduct(BaseModel):
    product_id: UUID
    variant_id: UUID
    title: str
    brand: str | None
    category: str | None
    price: Decimal
    currency: str
    availability: Literal["available", "unavailable", "unknown"]
    verified_attributes: dict[str, str]
    normalized_attributes: dict[str, str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class ProductComparisonResult(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    response_type: Literal["comparison", "clarification"]
    explanation: str
    products: list[ComparedProduct] = Field(default_factory=list, max_length=4)
    differences: list[str] = Field(default_factory=list, max_length=20)
    trade_offs: list[str] = Field(default_factory=list, max_length=12)
    limitations: list[str] = Field(default_factory=list, max_length=8)


class RecommendationExecutionOut(BaseModel):
    id: UUID
    kind: Literal["recommendation"] = "recommendation"
    status: Literal["queued", "running", "succeeded", "failed"]
    result: RecommendationResult | None = Field(default=None, validation_alias=AliasChoices("recommendation_result", "result"))
    safe_summary: str | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
