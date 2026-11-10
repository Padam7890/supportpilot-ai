"""Verified catalog conversation follow-ups; channel-neutral and store-bound."""
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogProduct, CatalogVariant, Conversation
from app.features.ai.application.catalog_discovery import ProductListing

_CONTEXT_KEY = "catalog_browse"
_TTL = timedelta(minutes=30)


def is_catalog_follow_up(message: str) -> bool:
    text = message.casefold().strip()
    return bool(re.search(
        r"\b(?:best|cheapest|lowest price|most expensive|compare|among these|"
        r"which one|first one|second one|details|tell me about|available|"
        r"in stock|recommend)\b", text,
    ))


def remember_catalog(conversation: Conversation, products: list[ProductListing], connection_id: UUID) -> None:
    """Keep only IDs, not model-authored product descriptions or prices."""
    state = dict(conversation.shopping_state or {})
    state[_CONTEXT_KEY] = {
        "connection_id": str(connection_id),
        "product_ids": list(dict.fromkeys(str(p.product_id) for p in products))[:30],
    }
    conversation.shopping_state = state
    conversation.shopping_state_updated_at = datetime.now(UTC)
    conversation.shopping_state_expires_at = datetime.now(UTC) + _TTL


async def answer_catalog_follow_up(
    db: AsyncSession, conversation: Conversation, organization_id: UUID,
    connection_id: UUID, message: str,
) -> str | None:
    """Re-query authorized catalog; never trust stale cached price or product facts."""
    state = conversation.shopping_context or {}
    browse = state.get(_CONTEXT_KEY)
    if not isinstance(browse, dict) or browse.get("connection_id") != str(connection_id):
        return None
    ids = browse.get("product_ids", [])
    if not isinstance(ids, list) or not ids:
        return None
    try:
        product_ids = [UUID(value) for value in ids[:30]]
    except (TypeError, ValueError, AttributeError):
        return None
    rows = (await db.execute(
        select(CatalogProduct, CatalogVariant)
        .join(CatalogVariant, (
            (CatalogVariant.product_id == CatalogProduct.id)
            & (CatalogVariant.organization_id == organization_id)
            & (CatalogVariant.connection_id == connection_id)
        ))
        .where(
            CatalogProduct.organization_id == organization_id,
            CatalogProduct.connection_id == connection_id,
            CatalogProduct.id.in_(product_ids),
            CatalogProduct.status == "active",
            CatalogProduct.deleted_at.is_(None),
            CatalogVariant.deleted_at.is_(None),
            CatalogVariant.availability != "unavailable",
        )
    )).all()
    if not rows:
        return "Those products are no longer available in the connected catalog."
    by_id = {}
    for product, variant in rows:
        by_id.setdefault(product.id, (product, variant))
        if variant.price < by_id[product.id][1].price:
            by_id[product.id] = (product, variant)
    products = [by_id[pid] for pid in product_ids if pid in by_id]
    normalized = " ".join(message.casefold().split())
    selected = next(
        ((p, v) for p, v in products if p.title.casefold() in normalized),
        None,
    )
    if selected is None:
        ordinal = re.search(r"\b(first|second|third)\s+(?:one|product|item)\b", normalized)
        position = {"first": 0, "second": 1, "third": 2}
        if ordinal and position[ordinal.group(1)] < len(products):
            selected = products[position[ordinal.group(1)]]
    if selected is not None:
        product, variant = selected
        description = (product.description or "").strip()
        return (
            f"{product.title} — {variant.price:.2f} {variant.currency}. "
            f"Availability: {variant.availability}. "
            + (f"Description: {description[:700]}. " if description else "")
            + (f"Product page: {product.canonical_url}" if product.canonical_url else "")
        ).strip()
    if not is_catalog_follow_up(message):
        return None
    currencies = {variant.currency for _, variant in products}
    if len(currencies) != 1:
        return "These products use different currencies, so I can't rank their prices directly. Which product would you like to explore?"
    if re.search(r"\b(cheapest|lowest price|least expensive|budget)\b", normalized):
        product, variant = min(products, key=lambda item: item[1].price)
        return f"The lowest-priced product in the previous list is {product.title} at {variant.price:.2f} {variant.currency}."
    if re.search(r"\b(most expensive|highest price)\b", normalized):
        product, variant = max(products, key=lambda item: item[1].price)
        return f"The highest-priced product in the previous list is {product.title} at {variant.price:.2f} {variant.currency}."
    if re.search(r"\b(best|recommend|which one)\b", normalized):
        return (
            "I can help choose among the products I just listed. "
            "What matters most to you: price, intended use, or specific features? "
            "I won't call one the best without knowing your priorities."
        )
    if re.search(r"\b(compare|among these)\b", normalized):
        lines = ["Here is a price comparison of the products from the previous list:"]
        lines.extend(f"- {p.title}: {v.price:.2f} {v.currency}" for p, v in products[:10])
        return "\n".join(lines) + "\nWhich features matter most to you?"
    return None
