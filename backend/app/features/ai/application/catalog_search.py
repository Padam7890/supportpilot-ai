"""Tenant-filtered PostgreSQL catalog retrieval for recommendation workflows."""

from uuid import UUID

from sqlalchemy import String, cast, func, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.ai.application.intent_extraction import _fallback_intent
from app.features.ai.domain.catalog import CatalogCandidate, _terms, category_aliases
from app.models import CatalogProduct, CatalogVariant, IntegrationConnection

MAX_CATALOG_CANDIDATES = 1000


async def load_candidates(
    db: AsyncSession, organization_id: UUID, question: str
) -> tuple[list[CatalogCandidate], list[str], list[str]]:
    terms = _terms(question)
    for alias in category_aliases(_fallback_intent(question).category):
        terms.extend(_terms(alias))
    terms = list(dict.fromkeys(terms))[:24]
    base_stmt = (
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
            CatalogProduct.status == "active",
            CatalogProduct.deleted_at.is_(None),
            CatalogVariant.organization_id == organization_id,
            CatalogVariant.deleted_at.is_(None),
            CatalogVariant.availability != "unavailable",
            IntegrationConnection.status == "connected",
        )
    )
    stmt = base_stmt
    if terms:
        search_document = literal_column(
            "to_tsvector('simple'::regconfig, "
            "coalesce(catalog_products.title, '') || ' ' || "
            "coalesce(catalog_products.description, '') || ' ' || "
            "coalesce(catalog_products.brand, '') || ' ' || "
            "coalesce(catalog_products.category, '') || ' ' || "
            "coalesce(catalog_products.specifications::text, ''))"
        )
        term_query = func.to_tsquery(literal_column("'simple'::regconfig"), " | ".join(terms))
        variant_match = or_(
            *[cast(CatalogVariant.attributes, String).ilike(f"%{term}%") for term in terms]
        )
        stmt = stmt.where(or_(search_document.op("@@")(term_query), variant_match))
    rows = (
        await db.execute(
            stmt.order_by(
                CatalogProduct.updated_at.desc(), CatalogProduct.id, CatalogVariant.id
            ).limit(MAX_CATALOG_CANDIDATES)
        )
    ).all()
    if terms and not rows:
        # Keep an empty text hit distinct from an actually empty tenant catalog.
        rows = (
            await db.execute(
                base_stmt.order_by(
                    CatalogProduct.updated_at.desc(), CatalogProduct.id, CatalogVariant.id
                ).limit(MAX_CATALOG_CANDIDATES)
            )
        ).all()
    candidates = [CatalogCandidate(product=product, variant=variant) for product, variant in rows]
    categories = sorted(
        {
            item.product.category.strip()
            for item in candidates
            if item.product.category and item.product.category.strip()
        }
    )
    brands = sorted(
        {
            item.product.brand.strip()
            for item in candidates
            if item.product.brand and item.product.brand.strip()
        }
    )
    return candidates, categories, brands


async def catalog_has_active_products(db: AsyncSession, organization_id: UUID) -> bool:
    product_id = await db.scalar(
        select(CatalogProduct.id)
        .join(
            IntegrationConnection,
            (IntegrationConnection.id == CatalogProduct.connection_id)
            & (IntegrationConnection.organization_id == organization_id),
        )
        .where(
            CatalogProduct.organization_id == organization_id,
            CatalogProduct.status == "active",
            CatalogProduct.deleted_at.is_(None),
            IntegrationConnection.status == "connected",
        )
        .limit(1)
    )
    return product_id is not None
