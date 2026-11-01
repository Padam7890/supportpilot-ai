"""Closed set of validated recommendation tools exposed to conversation AI."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.recommendations import (
    ProductComparisonResult,
    RecommendationIntent,
    RecommendationResult,
)


class ToolReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: UUID
    variant_id: UUID


class DisplayedRecommendationRef(ToolReference):
    available_variant_ids: list[UUID] = Field(default_factory=list, max_length=25)


class RecommendProductsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: RecommendationIntent
    rejected_product_ids: list[UUID] = Field(default_factory=list, max_length=50)


class CompareProductsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    products: list[ToolReference] = Field(min_length=2, max_length=4)

    @model_validator(mode="after")
    def products_are_distinct(self):
        if len({product.product_id for product in self.products}) != len(self.products):
            raise ValueError("Comparison requires different products")
        return self


class RecommendationToolOutput(BaseModel):
    tool: Literal["recommend_products"] = "recommend_products"
    result: RecommendationResult


class ComparisonToolOutput(BaseModel):
    tool: Literal["compare_products"] = "compare_products"
    result: ProductComparisonResult


TOOL_INPUT_SCHEMAS: dict[str, type[BaseModel]] = {
    "recommend_products": RecommendProductsInput,
    "compare_products": CompareProductsInput,
}


def validate_tool_input(name: str, payload: dict[str, object]) -> BaseModel:
    schema = TOOL_INPUT_SCHEMAS.get(name)
    if schema is None:
        raise ValueError("Unsupported recommendation tool")
    return schema.model_validate(payload)
