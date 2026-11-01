"""Deterministic comparison of verified catalog facts."""

import re
from decimal import Decimal

from app.schemas.recommendations import ComparedProduct, ProductComparisonResult

_UNIT_VALUE = re.compile(
    r"^\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mah|ah|tb|gb|kg|g|cm|mm|inches|inch|in)\s*$",
    re.IGNORECASE,
)
_UNIT_CONVERSIONS: dict[str, tuple[str, Decimal]] = {
    "mah": ("mAh", Decimal(1)),
    "ah": ("mAh", Decimal(1000)),
    "gb": ("GB", Decimal(1)),
    "tb": ("GB", Decimal(1000)),
    "g": ("g", Decimal(1)),
    "kg": ("g", Decimal(1000)),
    "mm": ("cm", Decimal("0.1")),
    "cm": ("cm", Decimal(1)),
    "in": ("cm", Decimal("2.54")),
    "inch": ("cm", Decimal("2.54")),
    "inches": ("cm", Decimal("2.54")),
}


def _normalize_attribute_value(value: str) -> tuple[Decimal, str, str] | None:
    match = _UNIT_VALUE.fullmatch(value)
    if not match:
        return None
    unit, raw_value = match.group("unit").casefold(), Decimal(match.group("value"))
    canonical_unit, multiplier = _UNIT_CONVERSIONS[unit]
    normalized = (raw_value * multiplier).normalize()
    number = format(normalized, ",f")
    return normalized, canonical_unit, f"{number} {canonical_unit}"


def compare_verified_products(
    products: list[ComparedProduct], *, priorities: list[str] | None = None
) -> ProductComparisonResult:
    """Create a deterministic comparison from verified catalog fields only."""
    if not 2 <= len(products) <= 4:
        return ProductComparisonResult(
            response_type="clarification",
            explanation="Choose 2–4 different products from the current recommendations to compare.",
        )

    normalized_products: list[ComparedProduct] = []
    for product in products:
        normalized_attributes: dict[str, str] = {}
        for key, value in product.verified_attributes.items():
            parsed = _normalize_attribute_value(value)
            if parsed is not None:
                normalized_attributes[key] = (
                    parsed[2]
                    if parsed[2].casefold() == value.casefold()
                    else f"{parsed[2]} (catalog: {value})"
                )
        normalized_products.append(product.model_copy(update={"normalized_attributes": normalized_attributes}))

    keys_by_folded: dict[str, str] = {}
    for product in normalized_products:
        for key in product.verified_attributes:
            keys_by_folded.setdefault(key.casefold(), key)
    rows: dict[str, list[tuple[ComparedProduct, str | None, tuple[Decimal, str, str] | None]]] = {}
    for folded in keys_by_folded:
        rows[folded] = []
        for product in normalized_products:
            key = next((candidate for candidate in product.verified_attributes if candidate.casefold() == folded), None)
            raw = product.verified_attributes.get(key) if key else None
            rows[folded].append((product, raw, _normalize_attribute_value(raw) if raw else None))

    differences: list[str] = []
    brands = list(dict.fromkeys(product.brand for product in normalized_products if product.brand))
    categories = list(dict.fromkeys(product.category for product in normalized_products if product.category))
    if len(brands) > 1:
        differences.append("Brands: " + "; ".join(f"{p.title}: {p.brand or 'Not listed'}" for p in normalized_products))
    if len(categories) > 1:
        differences.append("Categories: " + "; ".join(f"{p.title}: {p.category or 'Not listed'}" for p in normalized_products))
    currencies = {product.currency.upper() for product in normalized_products}
    prices = [product.price for product in normalized_products]
    if len(currencies) == 1 and len(set(prices)) > 1:
        differences.append(f"Prices range from {min(prices)} to {max(prices)} {normalized_products[0].currency}.")
    elif len(currencies) > 1:
        differences.append("Prices use different currencies and are not directly comparable.")
    if len({product.availability for product in normalized_products}) > 1:
        differences.append("Availability differs: " + "; ".join(f"{p.title}: {p.availability}" for p in normalized_products))

    for folded, values in rows.items():
        present_raw = {raw.casefold() for _product, raw, _normalized in values if raw}
        comparable = [normalized for _product, _raw, normalized in values if normalized]
        normalized_units = {value[1] for value in comparable}
        normalized_values = {value[0] for value in comparable}
        if all(raw is not None for _product, raw, _normalized in values) and len(comparable) == len(values) and len(normalized_units) == 1 and len(normalized_values) == 1:
            continue
        if len(present_raw) <= 1 and all(raw is not None for _product, raw, _normalized in values):
            continue
        display_key = keys_by_folded[folded]
        cells = []
        for product, raw, normalized in values:
            value = normalized[2] if normalized is not None and len(normalized_units) == 1 else raw or "Not listed"
            cells.append(f"{product.title}: {value}")
        differences.append(f"{display_key}: " + "; ".join(cells))

    trade_offs: list[str] = []
    for priority in list(dict.fromkeys((priorities or [])[:8])):
        folded_priority = priority.casefold()
        matching_rows = [
            (key, values) for key, values in rows.items()
            if folded_priority in key or key in folded_priority
        ]
        if not matching_rows:
            trade_offs.append(f"Your {priority} priority is not listed as a verified specification for these options.")
            continue
        key, values = matching_rows[0]
        display_key = keys_by_folded[key]
        cells = []
        for product, raw, normalized in values:
            shown = normalized[2] if normalized is not None else raw
            cells.append(f"{product.title}: {shown or 'not listed'}")
        trade_offs.append(f"For your {priority} priority ({display_key}), the catalog lists " + "; ".join(cells) + ".")

    completed = [
        product.model_copy(update={
            "limitations": product.limitations or ["The catalog has no structured specifications for this product."],
        })
        for product in normalized_products
    ]
    explanation = "Here are verified catalog differences"
    if priorities:
        explanation += " and how they relate to your stated priorities"
    explanation += ". Missing specifications are shown as not listed."
    return ProductComparisonResult(
        response_type="comparison", explanation=explanation, products=completed,
        differences=differences[:20], trade_offs=trade_offs[:12],
        limitations=["Prices and availability reflect the latest catalog sync and can change; confirm details on the store product page."],
    )
