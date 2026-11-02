"""Deterministic recommendation ranking and grounded response construction."""

import re
from decimal import Decimal
from uuid import UUID

from app.features.ai.domain.catalog import (
    CATEGORY_SYNONYMS,
    CatalogCandidate,
    _terms,
    candidate_matches_category,
    normalize_category,
)
from app.schemas.recommendations import (
    AppliedCriteria,
    RecommendationIntent,
    RecommendationResult,
    RecommendedProduct,
)

MAX_SOFT_BUDGET_OVERAGE = Decimal("0.20")


def _recommendation_follow_ups(category: str | None, result_count: int) -> list[str]:
    if not result_count:
        return ["Try a different product category", "Talk to a support teammate"]
    canonical = normalize_category(category)
    plural = {
        "phone": "phones",
        "laptop": "laptops",
        "earbuds": "earbuds",
        "tv": "TVs",
        "fridge": "fridges",
    }.get(canonical, f"{canonical}s" if canonical else "products")
    if canonical == "phone":
        return ["Which phone mentions camera details?", "Show cheaper options", "Find alternatives"]
    if canonical == "laptop":
        return [
            "Which laptop mentions battery details?",
            "Show cheaper options",
            "Find alternatives",
        ]
    return [f"Show more {plural}", "Show cheaper options", "Find alternatives"]


def _matches_feature(feature: str, text: str) -> bool:
    if feature.casefold() in text:
        return True
    descriptors = {
        "good",
        "great",
        "excellent",
        "strong",
        "long",
        "quality",
        "with",
        "and",
        "for",
        "a",
        "an",
        "the",
        "life",
    }
    tokens = [
        token for token in re.findall(r"[\w]+", feature.casefold()) if token not in descriptors
    ]
    return bool(tokens) and all(token in text for token in tokens)


def _clarification(
    message: str, *, criteria: AppliedCriteria | None = None
) -> RecommendationResult:
    return RecommendationResult(
        response_type="clarification",
        explanation=message,
        applied_criteria=criteria,
        suggested_follow_ups=[],
        available_actions=["refine_search"],
    )


def _candidate_reasons(
    candidate: CatalogCandidate,
    intent: RecommendationIntent,
    soft_preference_weights: dict[str, int] | None = None,
    ranking_preferences: dict[str, int] | None = None,
) -> tuple[list[str], list[str], int]:
    reasons: list[str] = []
    limitations: list[str] = []
    text = candidate.searchable_text
    if intent.category:
        category_match = (
            intent.category.casefold()
            in " ".join((candidate.product.category or "", candidate.product.title)).casefold()
        )
        if category_match:
            reasons.append(f"Matches the requested {intent.category} category")
    feature_hits = [
        feature for feature in intent.required_features if _matches_feature(feature, text)
    ]
    for feature in feature_hits:
        reasons.append(f"Catalog information mentions {feature}")
    optional_hits = [
        preference
        for preference in intent.optional_preferences
        if _matches_feature(preference, text)
    ]
    for preference in optional_hits:
        reasons.append(f"Catalog information matches the preference {preference}")
    if (
        candidate.product.brand
        and intent.preferred_brand
        and candidate.product.brand.casefold() == intent.preferred_brand.casefold()
    ):
        reasons.append(f"Brand matches {candidate.product.brand}")
    if candidate.variant.availability == "available":
        reasons.append("Variant is marked available in the latest catalog sync")
    else:
        limitations.append("Availability is unknown in the latest catalog sync")
    if intent.budget_amount is not None and candidate.variant.price <= intent.budget_amount:
        reasons.append("Price is within the stated budget")
    if not candidate.product.specifications:
        limitations.append("Structured product specifications are not available")
    available_signals = 0
    score = 0
    ranking = ranking_preferences or {}
    feature_weight = ranking.get("feature_match", 30)
    brand_weight = ranking.get("brand", 10)
    budget_weight = ranking.get("budget_fit", 15)
    use_case_weight = ranking.get("use_case", 10)
    if intent.category:
        available_signals += 20
        if (
            intent.category.casefold()
            in " ".join((candidate.product.category or "", candidate.product.title)).casefold()
        ):
            score += 20
    if intent.required_features:
        available_signals += feature_weight
        score += round(feature_weight * len(feature_hits) / len(intent.required_features))
    else:
        score += feature_weight
        available_signals += feature_weight
    if intent.optional_preferences:
        available_signals += 15
        weights = soft_preference_weights or {}
        total_weight = sum(
            max(1, min(5, weights.get(preference.casefold(), 1)))
            for preference in intent.optional_preferences
        )
        matched_weight = sum(
            max(1, min(5, weights.get(preference.casefold(), 1))) for preference in optional_hits
        )
        score += round(15 * matched_weight / total_weight) if total_weight else 0
    else:
        score += 15
        available_signals += 15
    if intent.preferred_brand:
        available_signals += brand_weight
        if (
            candidate.product.brand
            and candidate.product.brand.casefold() == intent.preferred_brand.casefold()
        ):
            score += brand_weight
    else:
        score += brand_weight
        available_signals += brand_weight
    if intent.use_case:
        available_signals += use_case_weight
        use_case_terms = _terms(intent.use_case)
        score += (
            round(
                use_case_weight * sum(term in text for term in use_case_terms) / len(use_case_terms)
            )
            if use_case_terms
            else 0
        )
    else:
        score += use_case_weight
        available_signals += use_case_weight
    if intent.budget_amount is not None and intent.budget_amount > 0:
        available_signals += budget_weight
        score += round(
            budget_weight
            * max(Decimal(0), Decimal(1) - candidate.variant.price / intent.budget_amount)
        )
    else:
        score += budget_weight
        available_signals += budget_weight
    # Scores are normalized to observed request criteria; missing reviews do not lower scores.
    score = round(score * 100 / available_signals) if available_signals else 0
    return reasons[:5], limitations, max(0, min(score, 100))


def _verified_attributes(candidate: CatalogCandidate) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for source in (candidate.variant.attributes, candidate.product.specifications):
        for key, value in source.items():
            if isinstance(value, (str, int, float, bool)):
                attributes[str(key)[:80]] = str(value)[:255]
            if len(attributes) >= 12:
                return attributes
    return attributes


def build_recommendation_result(
    question: str,
    intent: RecommendationIntent,
    candidates: list[CatalogCandidate],
    *,
    soft_preference_weights: dict[str, int] | None = None,
    ranking_preferences: dict[str, int] | None = None,
    catalog_empty: bool = True,
) -> RecommendationResult:
    intent = intent.model_copy(update={"category": normalize_category(intent.category)})
    criteria = AppliedCriteria(
        category=intent.category,
        budget_amount=intent.budget_amount,
        budget_currency=intent.budget_currency,
        budget_strict=intent.budget_strict,
        preferred_brand=intent.preferred_brand,
        required_brand=intent.required_brand,
        excluded_brands=intent.excluded_brands,
        required_features=intent.required_features,
        optional_preferences=intent.optional_preferences,
        use_case=intent.use_case,
        sort_by=intent.sort_by,
    )
    if not intent.is_recommendation:
        return RecommendationResult(
            response_type="unsupported",
            explanation="I can help compare and recommend products from this store’s catalog.",
            suggested_follow_ups=["Tell me what product you need and what matters most."],
            available_actions=["refine_search"],
        )
    if not candidates:
        if catalog_empty:
            explanation = "Sorry, this store’s product catalog is empty right now. Please check back soon or contact the store team."
            limitations = ["No active catalog products are available."]
            follow_ups = ["Talk to a support teammate"]
        else:
            explanation = "Sorry, I couldn’t find products matching that request right now. Would you like to explore another category?"
            limitations = []
            follow_ups = _recommendation_follow_ups(intent.category, 0)
        return RecommendationResult(
            response_type="no_match",
            explanation=explanation,
            applied_criteria=criteria,
            limitations=limitations,
            suggested_follow_ups=follow_ups,
            available_actions=["refine_search"],
        )
    if intent.category and not any(
        candidate_matches_category(item, intent.category) for item in candidates
    ):
        if normalize_category(intent.category) not in CATEGORY_SYNONYMS:
            return _clarification(
                "I’m not sure which type of product you mean. Could you describe it another way?",
                criteria=criteria,
            )
        return RecommendationResult(
            response_type="no_match",
            explanation=f"Sorry, I couldn’t find any {intent.category}s available right now. Would you like to explore something else?",
            applied_criteria=criteria,
            suggested_follow_ups=_recommendation_follow_ups(intent.category, 0),
            available_actions=["refine_search"],
        )
    currencies = {item.variant.currency.upper() for item in candidates}
    if intent.budget_amount is not None and intent.budget_currency is None:
        if len(currencies) != 1:
            return _clarification(
                "Which currency should I use for your budget? I won’t convert between currencies.",
                criteria=criteria,
            )
        intent = intent.model_copy(update={"budget_currency": next(iter(currencies))})
        criteria = criteria.model_copy(update={"budget_currency": intent.budget_currency})
    if intent.budget_amount is not None and intent.budget_currency is None:
        return _clarification("What currency should I use for that budget?", criteria=criteria)
    matching = [item for item in candidates if item.variant.availability != "unavailable"]
    if intent.required_brand:
        matching = [
            item
            for item in matching
            if item.product.brand
            and item.product.brand.casefold() == intent.required_brand.casefold()
        ]
    has_preferences = any(
        (
            intent.category,
            intent.budget_amount,
            intent.preferred_brand,
            intent.required_brand,
            intent.excluded_brands,
            intent.required_features,
            intent.optional_preferences,
            intent.use_case,
        )
    )
    if not has_preferences:
        return _clarification(
            "What kind of product are you looking for, and which features matter most?",
            criteria=criteria,
        )
    if intent.category:
        matching = [item for item in matching if candidate_matches_category(item, intent.category)]
    if intent.excluded_brands:
        excluded = {brand.casefold() for brand in intent.excluded_brands}
        matching = [
            item
            for item in matching
            if not item.product.brand or item.product.brand.casefold() not in excluded
        ]
    if intent.required_features:
        matching = [
            item
            for item in matching
            if all(
                _matches_feature(feature, item.searchable_text)
                for feature in intent.required_features
            )
        ]
    if intent.budget_amount is not None:
        matching = [
            item for item in matching if item.variant.currency.upper() == intent.budget_currency
        ]
        if intent.budget_strict:
            matching = [item for item in matching if item.variant.price <= intent.budget_amount]
        else:
            ceiling = intent.budget_amount * (Decimal(1) + MAX_SOFT_BUDGET_OVERAGE)
            matching = [item for item in matching if item.variant.price <= ceiling]
    if not matching:
        return RecommendationResult(
            response_type="no_match",
            explanation="I couldn’t find products that meet all those preferences, and I haven’t relaxed your budget or required criteria. Would you like to adjust one?",
            applied_criteria=criteria,
            limitations=["No matching products met every requested constraint."],
            suggested_follow_ups=_recommendation_follow_ups(intent.category, 0),
            available_actions=["refine_search"],
        )

    ranked: list[tuple[int, CatalogCandidate, list[str], list[str]]] = []
    for item in matching:
        reasons, limitations, score = _candidate_reasons(
            item, intent, soft_preference_weights, ranking_preferences
        )
        ranked.append((score, item, reasons, limitations))
    if intent.sort_by == "price_asc":
        ranked.sort(
            key=lambda row: (row[1].variant.price, -row[0], row[1].product.id, row[1].variant.id)
        )
    elif intent.sort_by == "price_desc":
        ranked.sort(
            key=lambda row: (-row[1].variant.price, -row[0], row[1].product.id, row[1].variant.id)
        )
    else:
        ranked.sort(
            key=lambda row: (-row[0], row[1].variant.price, row[1].product.id, row[1].variant.id)
        )
    unique_ranked: list[tuple[int, CatalogCandidate, list[str], list[str]]] = []
    seen_products: set[UUID] = set()
    for row in ranked:
        if row[1].product.id in seen_products:
            continue
        unique_ranked.append(row)
        seen_products.add(row[1].product.id)
    selected: list[tuple[int, CatalogCandidate, list[str], list[str]]] = []
    seen_products.clear()
    while unique_ranked and len(selected) < intent.result_count:
        current = unique_ranked.pop(0)
        if intent.preferred_brand is None and selected:
            current_brand = (current[1].product.brand or "").casefold()
            previous_brand = (selected[-1][1].product.brand or "").casefold()
            if current_brand and current_brand == previous_brand:
                alternative_index = next(
                    (
                        index
                        for index, row in enumerate(unique_ranked)
                        if row[1].product.id not in seen_products
                        and (row[1].product.brand or "").casefold() != current_brand
                        and row[0] >= current[0] - 5
                    ),
                    None,
                )
                if alternative_index is not None:
                    unique_ranked.insert(0, current)
                    current = unique_ranked.pop(alternative_index + 1)
        if current[1].product.id in seen_products:
            continue
        selected.append(current)
        seen_products.add(current[1].product.id)
    products = []
    for score, item, reasons, limitations in selected:
        overage = (
            max(Decimal(0), item.variant.price - intent.budget_amount)
            if intent.budget_amount is not None
            else Decimal(0)
        )
        if overage:
            limitations.append(f"{overage} {item.variant.currency} above your flexible budget")
        image = (
            item.product.images[0].get("url")
            if item.product.images and isinstance(item.product.images[0], dict)
            else None
        )
        attributes = _verified_attributes(item)
        variant_options = []
        for option in matching:
            if option.product.id != item.product.id:
                continue
            option_reasons, option_limitations, _option_score = _candidate_reasons(
                option, intent, soft_preference_weights, ranking_preferences
            )
            option_attributes = _verified_attributes(option)
            variant_options.append(
                {
                    "variant_id": option.variant.id,
                    "variant_title": option.variant.title,
                    "price": option.variant.price,
                    "currency": option.variant.currency,
                    "availability": option.variant.availability,
                    "verified_attributes": option_attributes,
                    "reasons": option_reasons,
                    "limitations": option_limitations,
                }
            )
            if len(variant_options) >= 25:
                break
        products.append(
            RecommendedProduct(
                product_id=item.product.id,
                variant_id=item.variant.id,
                title=item.product.title,
                variant_title=item.variant.title,
                brand=item.product.brand,
                category=item.product.category,
                price=item.variant.price,
                currency=item.variant.currency,
                availability=item.variant.availability,
                image_url=image,
                product_url=item.product.canonical_url,
                verified_attributes=attributes,
                variant_options=variant_options,
                score=score,
                reasons=reasons,
                limitations=list(dict.fromkeys(limitations)),
                budget_overage=overage or None,
            )
        )
    limitations = [
        "Recommendations use catalog data from the last sync; confirm current price and availability on the product page."
    ]
    if not any(item.product.specifications for item in matching):
        limitations.append(
            "The catalog has limited structured specifications, so attribute matching may be incomplete."
        )
    plural = {
        "phone": "phones",
        "laptop": "laptops",
        "earbuds": "earbuds",
        "tv": "TVs",
        "fridge": "fridges",
    }.get(normalize_category(intent.category), "products")
    explanation = (
        f"Yes, we have an option in {plural} you can explore."
        if len(products) == 1
        else f"Yes, here are {len(products)} {plural} you can explore."
    )
    return RecommendationResult(
        response_type="recommendations",
        explanation=explanation,
        applied_criteria=criteria,
        products=products,
        limitations=limitations,
        available_actions=["view_product", "refine_search"],
        suggested_follow_ups=_recommendation_follow_ups(intent.category, len(products)),
    )
