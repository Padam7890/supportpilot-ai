"""Application-wide provider registration composition root."""

from app.integrations.core.registry import IntegrationRegistry
from app.integrations.providers.shopify.provider import ShopifyCatalogProvider
from app.services.catalog import resolve_shopify_credentials


def build_integration_registry() -> IntegrationRegistry:
    """Create the canonical registry with each implemented provider registered once."""
    registry = IntegrationRegistry()
    registry.register(ShopifyCatalogProvider(resolve_shopify_credentials))
    return registry
