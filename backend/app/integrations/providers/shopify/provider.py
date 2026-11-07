"""Shopify provider descriptor for capabilities implemented in this release."""

from app.integrations.core.contracts.provider import ProviderDescriptor
from app.integrations.core.types import IntegrationCapability
from app.integrations.providers.shopify.catalog import (
    CredentialResolver,
    ShopifyProductCatalogAdapter,
)
from app.integrations.providers.shopify.commerce import (
    CommerceCredentialResolver,
    ShopifyCommerceAdapter,
)
from app.integrations.providers.shopify.webhooks import ShopifyWebhookAdapter


class ShopifyCatalogProvider:
    def __init__(
        self,
        resolve_credentials: CredentialResolver,
        resolve_commerce_credentials: CommerceCredentialResolver,
    ) -> None:
        self._catalog = ShopifyProductCatalogAdapter(resolve_credentials)
        self._commerce = ShopifyCommerceAdapter(resolve_commerce_credentials)
        self._webhooks = ShopifyWebhookAdapter()
        self._descriptor = ProviderDescriptor(
            provider_id="shopify",
            display_name="Shopify",
            version="1",
            capabilities=frozenset(
                {
                    IntegrationCapability.COMMERCE,
                    IntegrationCapability.PRODUCT_CATALOG,
                    IntegrationCapability.WEBHOOKS,
                }
            ),
        )

    @property
    def descriptor(self) -> ProviderDescriptor:
        return self._descriptor

    def get_capability(self, capability: IntegrationCapability) -> object | None:
        if capability is IntegrationCapability.PRODUCT_CATALOG:
            return self._catalog
        if capability is IntegrationCapability.COMMERCE:
            return self._commerce
        if capability is IntegrationCapability.WEBHOOKS:
            return self._webhooks
        return None
