"""Resolve which playbook capabilities a tenant has (integrations, connectors)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import IntegrationConnection, ShopifyInstallation


async def organization_capabilities(db: AsyncSession, organization_id: UUID) -> frozenset[str]:
    """Stable capability tokens for marketplace gating and publish validation."""
    caps: set[str] = {"inbox", "widget"}
    shopify = await db.scalar(
        select(func.count())
        .select_from(ShopifyInstallation)
        .where(
            ShopifyInstallation.organization_id == organization_id,
            ShopifyInstallation.disconnected_at.is_(None),
        )
    )
    if int(shopify or 0) > 0:
        caps.add("shopify.read")

    rows = await db.scalars(
        select(IntegrationConnection.provider_id).where(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.status == "connected",
        )
    )
    for provider_id in rows:
        pid = (provider_id or "").casefold()
        if "whatsapp" in pid:
            caps.add("whatsapp.channel")
        if "messenger" in pid or "facebook" in pid:
            caps.add("messenger.channel")
    return frozenset(caps)


def missing_capabilities(
    required: list[str], *, available: frozenset[str]
) -> list[str]:
    return [r for r in required if r not in available]
