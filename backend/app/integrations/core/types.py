"""Shared primitive types for integration providers and capabilities."""

from enum import StrEnum


class IntegrationCapability(StrEnum):
    MESSAGING = "messaging"
    COMMERCE = "commerce"
    PRODUCT_CATALOG = "product_catalog"
    CART = "cart"
    CHECKOUT = "checkout"
    WEBHOOKS = "webhooks"
    SYNCHRONIZATION = "synchronization"
