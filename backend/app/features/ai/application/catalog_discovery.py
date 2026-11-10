"""Channel-independent, tenant-scoped product discovery.

The caller (widget, WhatsApp, Messenger or API) owns message transport.
Only synchronized products from a connected store can be returned.
"""
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CatalogProduct, CatalogVariant, IntegrationConnection


@dataclass(frozen=True)
class ProductListing:
    product_id: UUID
    variant_id: UUID
    title: str
    price: str
    currency: str
    availability: str


async def list_verified_products(
    db: AsyncSession, organization_id: UUID, *, limit: int = 10, offset: int = 0,
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
            product_id=product.id, variant_id=variant.id,
            title=product.title, price=str(variant.price),
            currency=variant.currency, availability=variant.availability,
        )
        for product, variant in rows
    ]
