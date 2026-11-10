"""Channel-independent, tenant-scoped product discovery.

The caller (widget, WhatsApp, Messenger or API) owns message transport.
Only synchronized products from a connected store can be returned.
"""
import re
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogProduct, CatalogVariant, IntegrationConnection


@dataclass(frozen=True)
class ProductListing:
    product_id: UUID
    connection_id: UUID
    variant_id: UUID
    title: str
    price: str
    currency: str
    availability: str


async def list_verified_products(
    db: AsyncSession, organization_id: UUID, *, connection_id: UUID, limit: int = 10, offset: int = 0,
) -> list[ProductListing]:
    """Return a bounded catalog page; never substitute knowledge excerpts."""
    if not 1 <= limit <= 30 or not 0 <= offset <= 10000:
        raise ValueError("Invalid catalog pagination")
    rows = (await db.execute(
        select(CatalogProduct, CatalogVariant)
        .join(CatalogVariant, (
            (CatalogVariant.product_id == CatalogProduct.id)
            & (CatalogVariant.organization_id == CatalogProduct.organization_id)
        ))
        .join(IntegrationConnection, (
            (IntegrationConnection.id == CatalogProduct.connection_id)
            & (IntegrationConnection.organization_id == organization_id)
        ))
        .where(
            CatalogProduct.organization_id == organization_id,
            CatalogProduct.connection_id == connection_id,
            CatalogProduct.status == "active",
            CatalogProduct.deleted_at.is_(None),
            CatalogVariant.organization_id == organization_id,
            CatalogVariant.deleted_at.is_(None),
            CatalogVariant.availability != "unavailable",
            IntegrationConnection.status == "connected",
        )
        .order_by(CatalogProduct.id, CatalogVariant.id)
        .offset(offset).limit(limit)
    )).all()
    return [
        ProductListing(
            product_id=product.id, connection_id=product.connection_id, variant_id=variant.id,
            title=product.title, price=str(variant.price),
            currency=variant.currency, availability=variant.availability,
        )
        for product, variant in rows
    ]

def is_catalog_discovery_request(message: str) -> bool:
    """Recognize explicit browse/list intent without requiring a product name."""
    normalized = " ".join(message.casefold().split())
    return bool(re.search(
        r"\\b(?:list|show|browse|see|view|display)\\s+(?:(?:me|all|your|the|available|some)\\s+){0,3}"
        r"(?:products|items|catalog|inventory)\\b"
        r"|\\bwhat\\s+(?:(?:kind|types?)\\s+of\\s+)?(?:products|items)\\s+"
        r"(?:do\\s+you\\s+have|are\\s+available|do\\s+you\\s+sell)\\b"
        r"|\\bwhat\\s+do\\s+you\\s+sell\\b",
        normalized,
    ))


def render_product_listing(products: list[ProductListing]) -> str:
    """Transport-neutral text fallback; adapters may render native product cards."""
    if not products:
        return "I couldn't find any currently available products in the connected catalog. Please ask the store team to confirm."
    lines = ["Here are products from the store's connected catalog:"]
    for item in products:
        lines.append(f"- {item.title} — {item.price} {item.currency}")
    lines.append("Would you like details about any of these?")
    return "\\n".join(lines)

async def resolve_catalog_connection(
    db: AsyncSession, organization_id: UUID, *, bound_connection_id: UUID | None,
) -> UUID | None:
    """Prefer server-bound connection; otherwise allow only an unambiguous singleton.

    Never let a model choose a store or silently mix multiple stores.
    """
    stmt = select(IntegrationConnection.id).where(
        IntegrationConnection.organization_id == organization_id,
        IntegrationConnection.status == "connected",
    )
    if bound_connection_id is not None:
        return await db.scalar(stmt.where(IntegrationConnection.id == bound_connection_id))
    connections = list((await db.scalars(stmt.limit(2))).all())
    return connections[0] if len(connections) == 1 else None
