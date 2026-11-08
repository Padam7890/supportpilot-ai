"""Resolve which playbook capabilities a tenant has (integrations, connectors)."""

from __future__ import annotations

from functools import lru_cache
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.core.contracts.provider import ProviderDescriptor
from app.integrations.core.types import IntegrationCapability
from app.integrations.providers.shopify.client import effective_shopify_scopes
from app.models import IntegrationConnection, ShopifyInstallation


@lru_cache(maxsize=1)
def _registered_providers() -> dict[str, ProviderDescriptor]:
    # Descriptors are immutable; cache the composition result for request and
    # worker calls rather than rebuilding adapters for every capability check.
    from app.integrations.registry import build_integration_registry

    return {
        descriptor.provider_id: descriptor
        for descriptor in build_integration_registry().list_providers()
    }


async def organization_capabilities(db: AsyncSession, organization_id: UUID) -> frozenset[str]:
    """Resolve only capabilities backed by a registered, connected provider."""
    # A database row alone must not make an unimplemented channel available.
    providers = _registered_providers()
    caps: set[str] = {"inbox", "widget"}
    shopify_provider = providers.get("shopify")
    shopify_grants = await db.scalar(
        select(ShopifyInstallation.granted_scopes).where(
            ShopifyInstallation.organization_id == organization_id,
            ShopifyInstallation.disconnected_at.is_(None),
        )
    )
    if (
        shopify_grants is not None
        and shopify_provider is not None
        and IntegrationCapability.COMMERCE in shopify_provider.capabilities
    ):
        effective_grants = effective_shopify_scopes(shopify_grants)
        caps.add("shopify.connected")
        if "read_orders" in effective_grants:
            caps.add("shopify.orders.read")
        if {"read_orders", "read_customers"}.issubset(effective_grants):
            caps.add("shopify.orders.verified_read")
        if (
            "read_products" in effective_grants
            and IntegrationCapability.PRODUCT_CATALOG in shopify_provider.capabilities
        ):
            caps.add("shopify.catalog.read")
            caps.add("shopify.read")
        if {"read_orders", "read_customers", "write_orders"}.issubset(effective_grants):
            caps.add("shopify.orders.cancel")
        if {"read_orders", "read_customers"}.issubset(effective_grants):
            caps.add("shopify.read")

    rows = await db.scalars(
        select(IntegrationConnection.provider_id).where(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.status == "connected",
        )
    )
    for provider_id in rows:
        pid = (provider_id or "").casefold()
        provider = providers.get(pid)
        if provider is None or IntegrationCapability.INBOUND_MESSAGING not in provider.capabilities:
            continue
        if pid == "whatsapp":
            caps.add("whatsapp.channel")
        elif pid in {"messenger", "facebook_messenger"}:
            caps.add("messenger.channel")
    return frozenset(caps)


def missing_capabilities(
    required: list[str], *, available: frozenset[str]
) -> list[str]:
    return [r for r in required if r not in available]
