"""Compatibility exports for the feature-oriented recommendation modules."""

from app.features.ai.application.catalog_search import catalog_has_active_products, load_candidates
from app.features.ai.application.intent_extraction import (
    _fallback_intent,
    extract_intent,
    parse_intent_output,
)
from app.features.ai.domain.catalog import (
    CatalogCandidate,
    _terms,
    candidate_matches_category,
    category_aliases,
    normalize_category,
)
from app.features.ai.domain.ranking import (
    MAX_SOFT_BUDGET_OVERAGE,
    build_recommendation_result,
)

__all__ = [
    "MAX_SOFT_BUDGET_OVERAGE",
    "CatalogCandidate",
    "_fallback_intent",
    "_terms",
    "build_recommendation_result",
    "candidate_matches_category",
    "catalog_has_active_products",
    "category_aliases",
    "extract_intent",
    "load_candidates",
    "normalize_category",
    "parse_intent_output",
]
