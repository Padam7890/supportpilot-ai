"""Compact, tenant-conversation-scoped shopping state and turn transitions."""

import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.ai.application.catalog_search import (
    catalog_has_active_products,
    load_candidates,
)
from app.features.ai.domain.ranking import build_recommendation_result
from app.features.ai.domain.shopping_state import (
    MAX_REJECTIONS_BEFORE_HANDOFF_OFFER,
    MAX_UNSUPPORTED_TURNS_BEFORE_HANDOFF_OFFER,
    SHOPPING_CUES,
    ShoppingConversationState,
    ShoppingTurnAnalysis,
    analyze_shopping_turn,
    apply_shopping_turn,
    fallback_turn_analysis,
    load_shopping_state,
    make_recommendation_intent,
    shopping_state_is_expired,
    should_consider_shopping_turn,
)
from app.features.ai.tools.recommendations import (
    CompareProductsInput,
    DisplayedRecommendationRef,
    RecommendationToolOutput,
    RecommendProductsInput,
    ToolReference,
    validate_tool_input,
)
from app.models import CatalogProduct, CatalogVariant, IntegrationConnection, RecommendationSettings
from app.schemas.recommendations import (
    ComparedProduct,
    ProductComparisonResult,
)
from app.services.product_comparison import compare_verified_products

__all__ = [
    "SHOPPING_CUES",
    "ShoppingConversationState",
    "ShoppingTurnAnalysis",
    "WidgetShoppingOutcome",
    "apply_shopping_turn",
    "fallback_turn_analysis",
    "invoke_recommend_products",
    "load_shopping_state",
    "process_widget_shopping_turn",
    "shopping_state_is_expired",
]


async def invoke_recommend_products(
    db: AsyncSession,
    organization_id: UUID,
    question: str,
    state: ShoppingConversationState,
) -> tuple[RecommendationToolOutput, list[DisplayedRecommendationRef]]:
    policy = (
        await db.scalar(
            select(RecommendationSettings).where(
                RecommendationSettings.organization_id == organization_id
            )
        )
        if db is not None
        else None
    )
    candidates, _categories, _brands = await load_candidates(db, organization_id, question)
    rejected = set(state.rejected_product_ids)
    excluded_products = {
        UUID(value) for value in (policy.excluded_product_ids if policy else []) if _is_uuid(value)
    }
    excluded_collections = set(policy.excluded_collection_ids if policy else [])
    eligible = [
        item
        for item in candidates
        if item.product.id not in rejected
        and item.product.id not in excluded_products
        and (not policy or not policy.in_stock_only or item.variant.availability == "available")
        and not (
            excluded_collections
            & {str(value) for value in item.product.specifications.get("collection_ids", [])}
        )
    ]
    intent = make_recommendation_intent(state)
    if policy:
        intent.result_count = min(intent.result_count, policy.max_products)
    catalog_empty = False
    if not candidates and db is not None:
        catalog_empty = not await catalog_has_active_products(db, organization_id)
    elif not candidates:
        catalog_empty = True
    tool_input = validate_tool_input(
        "recommend_products",
        {
            "intent": intent.model_dump(mode="json"),
            "rejected_product_ids": [str(value) for value in state.rejected_product_ids],
        },
    )
    if not isinstance(tool_input, RecommendProductsInput):
        raise TypeError("Recommendation tool input validation returned the wrong contract")
    result = build_recommendation_result(
        question,
        tool_input.intent,
        eligible,
        soft_preference_weights=state.soft_preferences,
        ranking_preferences=policy.ranking_preferences if policy else None,
        catalog_empty=catalog_empty,
    )
    refs = [
        DisplayedRecommendationRef(
            product_id=item.product_id,
            variant_id=item.variant_id,
            available_variant_ids=[option.variant_id for option in item.variant_options]
            or [item.variant_id],
        )
        for item in result.products
    ]
    return RecommendationToolOutput(result=result), refs


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, TypeError):
        return False


async def invoke_compare_products(
    db: AsyncSession,
    organization_id: UUID,
    references: list[ToolReference],
    priorities: list[str] | None = None,
) -> ProductComparisonResult:
    tool_input = validate_tool_input(
        "compare_products", {"products": [ref.model_dump(mode="json") for ref in references]}
    )
    if not isinstance(tool_input, CompareProductsInput):
        raise TypeError("Comparison tool input validation returned the wrong contract")
    product_ids = {ref.product_id for ref in tool_input.products}
    variant_ids = {ref.variant_id for ref in tool_input.products}
    rows = (
        await db.execute(
            select(CatalogProduct, CatalogVariant)
            .join(
                CatalogVariant,
                (CatalogVariant.product_id == CatalogProduct.id)
                & (CatalogVariant.organization_id == CatalogProduct.organization_id),
            )
            .join(
                IntegrationConnection,
                (IntegrationConnection.id == CatalogProduct.connection_id)
                & (IntegrationConnection.organization_id == organization_id),
            )
            .where(
                CatalogProduct.organization_id == organization_id,
                CatalogProduct.id.in_(product_ids),
                CatalogProduct.status == "active",
                CatalogProduct.deleted_at.is_(None),
                CatalogVariant.organization_id == organization_id,
                CatalogVariant.id.in_(variant_ids),
                CatalogVariant.deleted_at.is_(None),
                IntegrationConnection.status == "connected",
            )
        )
    ).all()
    by_pair = {(product.id, variant.id): (product, variant) for product, variant in rows}
    if any((ref.product_id, ref.variant_id) not in by_pair for ref in tool_input.products):
        return ProductComparisonResult(
            response_type="clarification",
            explanation="One of those products is no longer available in this store’s current catalog. Please ask me to show options again.",
        )
    compared: list[ComparedProduct] = []
    for ref in tool_input.products:
        product, variant = by_pair[(ref.product_id, ref.variant_id)]
        attributes: dict[str, str] = {}
        for source in (variant.attributes, product.specifications):
            for key, value in source.items():
                if isinstance(value, (str, int, float, bool)):
                    attributes[str(key)[:80]] = str(value)[:255]
                if len(attributes) >= 12:
                    break
            if len(attributes) >= 12:
                break
        compared.append(
            ComparedProduct(
                product_id=product.id,
                variant_id=variant.id,
                title=product.title,
                brand=product.brand,
                category=product.category,
                price=variant.price,
                currency=variant.currency,
                availability=variant.availability,
                verified_attributes=attributes,
                limitations=[]
                if attributes
                else ["The catalog has no structured specifications for this product."],
            )
        )
    return compare_verified_products(compared, priorities=priorities or [])


def render_recommendation_reply(output: RecommendationToolOutput) -> str:
    result = output.result
    if result.response_type != "recommendations" or not result.products:
        return result.explanation
    lines = [result.explanation]
    for index, product in enumerate(result.products, start=1):
        line = f"{index}. {product.title}"
        if product.variant_title and product.variant_title.casefold() not in {
            "default",
            "default title",
        }:
            line += f" ({product.variant_title})"
        line += f" — {product.price} {product.currency}"
        if product.brand:
            line += f" · {product.brand}"
        lines.append(line)
        if product.reasons:
            lines.append("   " + "; ".join(product.reasons[:3]) + ".")
        if product.limitations:
            lines.append("   Note: " + "; ".join(product.limitations[:2]) + ".")
        if product.product_url:
            lines.append(f"   {product.product_url}")
    return "\n".join(lines)


def render_comparison_reply(result: ProductComparisonResult) -> str:
    if result.response_type == "clarification":
        return result.explanation
    lines = [result.explanation]
    for index, item in enumerate(result.products, start=1):
        lines.append(
            f"{index}. {item.title} — {item.price} {item.currency}; availability: {item.availability}."
        )
        if item.verified_attributes:
            lines.append(
                "   Verified details: "
                + ", ".join(
                    f"{key}: {value}" for key, value in sorted(item.verified_attributes.items())[:8]
                )
                + "."
            )
        elif item.limitations:
            lines.append("   Note: " + item.limitations[0])
    if result.differences:
        lines.append("Differences: " + "; ".join(result.differences[:8]) + ".")
    else:
        lines.append(
            "The catalog does not show verified differences in the available comparison fields."
        )
    if result.trade_offs:
        lines.append("Based on your priorities: " + " ".join(result.trade_offs[:8]))
    if result.limitations:
        lines.append("Note: " + " ".join(result.limitations[:4]))
    return "\n".join(lines)


@dataclass(frozen=True)
class WidgetShoppingOutcome:
    handled: bool
    draft: str | None = None
    state: dict[str, object] | None = None
    displayed_recommendations: list[dict[str, object]] | None = None
    recommendation_payload: dict[str, object] | None = None
    usage: dict[str, int] | None = None
    model_name: str | None = None
    tool_outcomes: list[dict[str, str | int]] | None = None
    switch_to_human: bool = False


async def process_widget_shopping_turn(
    db: AsyncSession,
    organization_id: UUID,
    conversation_id: UUID,
    question: str,
    raw_state: dict | None,
    state_expires_at: datetime | None,
    selected_references: list[ToolReference] | None = None,
    allowed_tools: list[str] | None = None,
) -> WidgetShoppingOutcome:
    configured_tools = (
        allowed_tools
        if allowed_tools is not None
        else ["recommend_products", "compare_products"]
    )
    enabled_tools = set(configured_tools) & {"recommend_products", "compare_products"}
    state, _expired = load_shopping_state(raw_state, state_expires_at)
    if not should_consider_shopping_turn(question, state):
        return WidgetShoppingOutcome(handled=False)
    policy = (
        await db.scalar(
            select(RecommendationSettings).where(
                RecommendationSettings.organization_id == organization_id
            )
        )
        if db is not None
        else None
    )
    if policy is not None and not policy.enabled:
        return WidgetShoppingOutcome(
            handled=True,
            draft="Product recommendations are currently turned off for this store. I can pass your question to the support team.",
            switch_to_human=True,
        )
    if (
        policy is not None
        and policy.mode == "explicit"
        and not state.active
        and not re.search(
            r"\b(recommend|recommendation|suggest|show me|find me|looking for|sifaris|sujhab)\b|सिफारिस|सुझाव",
            question,
            re.IGNORECASE,
        )
    ):
        return WidgetShoppingOutcome(handled=False)
    if state.active and not SHOPPING_CUES.search(question):
        return WidgetShoppingOutcome(handled=False)
    _candidates, categories, brands = await load_candidates(db, organization_id, question)
    analysis, usage, model_name = await analyze_shopping_turn(
        question, state, categories=categories, brands=brands, allowed_tools=sorted(enabled_tools)
    )
    if analysis.action == "none":
        return WidgetShoppingOutcome(handled=False)
    handoff = policy.human_handoff_preferences if policy else {}
    state, action, references, override = apply_shopping_turn(
        state,
        analysis,
        rejected_threshold=int(
            handoff.get("rejected_threshold", MAX_REJECTIONS_BEFORE_HANDOFF_OFFER)
        ),
        unsupported_threshold=int(
            handoff.get("unsupported_threshold", MAX_UNSUPPORTED_TURNS_BEFORE_HANDOFF_OFFER)
        ),
        handoff_enabled=bool(handoff.get("enabled", True)),
    )
    if action == "none":
        return WidgetShoppingOutcome(handled=False)
    if action == "reset":
        return WidgetShoppingOutcome(
            handled=True,
            draft=override,
            state=None,
            usage=usage,
            model_name=model_name,
            tool_outcomes=[{"tool": "shopping_state", "status": "reset", "result_count": 0}],
        )
    if action in {"clarify", "unsupported", "handoff_offer", "handoff"}:
        reply = override or "Could you clarify what you’d like to compare or change?"
        return WidgetShoppingOutcome(
            handled=True,
            draft=reply,
            state=state.model_dump(mode="json"),
            usage=usage,
            model_name=model_name,
            switch_to_human=action == "handoff",
            tool_outcomes=[{"tool": "shopping_state", "status": action, "result_count": 0}],
        )
    if action == "compare":
        if "compare_products" not in enabled_tools:
            return WidgetShoppingOutcome(
                handled=True,
                draft="Product comparisons are not enabled for this assistant. I can still help you explore products or ask the store team for help.",
                state=state.model_dump(mode="json"),
                usage=usage,
                model_name=model_name,
                tool_outcomes=[{"tool": "compare_products", "status": "disabled", "result_count": 0}],
            )
        if policy is not None and not policy.comparison_enabled:
            return WidgetShoppingOutcome(
                handled=True,
                draft="Product comparison is currently turned off for this store. I can still answer questions about an individual product.",
                state=state.model_dump(mode="json"),
            )
        if selected_references is not None:
            valid_variants = {
                str(reference.product_id): {
                    str(value)
                    for value in (reference.available_variant_ids or [reference.variant_id])
                }
                for reference in state.last_displayed_recommendations
            }
            if (
                not 2 <= len(selected_references) <= 4
                or len({reference.product_id for reference in selected_references}) != 2
                or any(
                    str(reference.product_id) not in valid_variants
                    or str(reference.variant_id) not in valid_variants[str(reference.product_id)]
                    for reference in selected_references
                )
            ):
                state.clarification_state = "comparison_reference"
                return WidgetShoppingOutcome(
                    handled=True,
                    draft="Those selected options are no longer in the displayed recommendations. Please show the options again before comparing.",
                    state=state.model_dump(mode="json"),
                    tool_outcomes=[
                        {"tool": "shopping_state", "status": "invalid_selection", "result_count": 0}
                    ],
                )
            references = selected_references
            state.selected_products_for_comparison = selected_references
        intent = make_recommendation_intent(state)
        priorities = list(
            dict.fromkeys(
                intent.required_features
                + sorted(
                    state.soft_preferences, key=lambda name: (-state.soft_preferences[name], name)
                )
                + intent.optional_preferences
            )
        )[:8]
        comparison = await invoke_compare_products(db, organization_id, references, priorities)
        state.clarification_state = (
            "comparison_reference" if comparison.response_type == "clarification" else None
        )
        return WidgetShoppingOutcome(
            handled=True,
            draft=render_comparison_reply(comparison),
            state=state.model_dump(mode="json"),
            recommendation_payload=comparison.model_dump(mode="json"),
            usage=usage,
            model_name=model_name,
            tool_outcomes=[
                {
                    "tool": "compare_products",
                    "status": comparison.response_type,
                    "result_count": len(comparison.products),
                }
            ],
        )
    if "recommend_products" not in enabled_tools:
        return WidgetShoppingOutcome(
            handled=True,
            draft="Product recommendations are not enabled for this assistant. I can answer using its assigned knowledge sources or ask the store team to help.",
            state=state.model_dump(mode="json"),
            usage=usage,
            model_name=model_name,
            tool_outcomes=[{"tool": "recommend_products", "status": "disabled", "result_count": 0}],
        )
    recommendation, displayed = await invoke_recommend_products(
        db, organization_id, question, state
    )
    state.clarification_state = (
        "recommendation" if recommendation.result.response_type == "clarification" else None
    )
    if recommendation.result.response_type == "recommendations":
        state.handoff_offer_pending = False
    return WidgetShoppingOutcome(
        handled=True,
        draft=override or render_recommendation_reply(recommendation),
        state=state.model_dump(mode="json"),
        displayed_recommendations=[ref.model_dump(mode="json") for ref in displayed],
        recommendation_payload=recommendation.result.model_dump(mode="json"),
        usage=usage,
        model_name=model_name,
        tool_outcomes=[
            {
                "tool": "recommend_products",
                "status": recommendation.result.response_type,
                "result_count": len(recommendation.result.products),
            }
        ],
    )
