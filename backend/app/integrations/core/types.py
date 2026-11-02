"""Shared primitive types for integration providers and capabilities."""

from enum import StrEnum


class IntegrationCapability(StrEnum):
    MESSAGING = "messaging"
    INBOUND_MESSAGING = "inbound_messaging"
    OUTBOUND_MESSAGING = "outbound_messaging"
    COMMERCE = "commerce"
    PRODUCT_CATALOG = "product_catalog"
    CART = "cart"
    CHECKOUT = "checkout"
    WEBHOOKS = "webhooks"
    SYNCHRONIZATION = "synchronization"
