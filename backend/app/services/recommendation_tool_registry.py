"""Compatibility re-exports; recommendation tool schemas live in the AI feature."""

from app.features.ai.tools.recommendations import (
    TOOL_INPUT_SCHEMAS,
    CompareProductsInput,
    ComparisonToolOutput,
    DisplayedRecommendationRef,
    RecommendationToolOutput,
    RecommendProductsInput,
    ToolReference,
    validate_tool_input,
)

__all__ = [
    "TOOL_INPUT_SCHEMAS",
    "CompareProductsInput",
    "ComparisonToolOutput",
    "DisplayedRecommendationRef",
    "RecommendProductsInput",
    "RecommendationToolOutput",
    "ToolReference",
    "validate_tool_input",
]
