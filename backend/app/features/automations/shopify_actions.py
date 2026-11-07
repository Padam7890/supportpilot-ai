"""Read-only Shopify helpers for automation actions (tenant-scoped, no LLM)."""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.providers.shopify.catalog import ShopifyProductCatalogAdapter
from app.integrations.providers.shopify.client import ShopifyAPIError
from app.integrations.providers.shopify.orders import lookup_authorized_order
from app.models import Customer, Ticket
from app.services.catalog import (
    connected_shopify_connection,
    connection_ref,
    resolve_shopify_credentials,
)
from app.services.shopify_commerce_credentials import resolve_shopify_commerce_credentials

logger = logging.getLogger(__name__)

_DEFAULT_ORDER_PATTERN = re.compile(r"(#?[A-Za-z0-9-]{4,})")


def extract_order_number(message: str, pattern: str) -> str | None:
    try:
        rx = re.compile(pattern)
    except re.error:
        rx = _DEFAULT_ORDER_PATTERN
    m = rx.search(message)
    if not m:
        return None
    if m.lastindex:
        return m.group(1).strip()
    return m.group(0).strip()


def extract_catalog_query(message: str, query_regex: str | None) -> str | None:
    if query_regex:
        try:
            rx = re.compile(query_regex, re.IGNORECASE)
        except re.error:
            return None
        m = rx.search(message)
        if not m:
            return None
        if m.lastindex:
            return m.group(1).strip()
        return m.group(0).strip()
    words = message.strip().split()
    if len(words) >= 2:
        return " ".join(words[-2:])[:120]
    if words:
        return words[-1][:120]
    return None


async def read_shopify_order_summary(
    db: AsyncSession, organization_id: UUID, *, order_number: str, customer_email: str
) -> tuple[bool, str]:
    """Return (found, short summary or error code)."""
    try:
        _installation, connection = await connected_shopify_connection(db, organization_id)
    except LookupError:
        return False, "shopify_not_connected"

    try:
        shop_domain, token, _scopes = await resolve_shopify_commerce_credentials(
            connection_ref(connection)
        )
        order = await lookup_authorized_order(
            shop_domain=shop_domain,
            access_token=token,
            order_number=order_number,
            customer_email=customer_email,
        )
    except ShopifyAPIError as exc:
        logger.warning(
            "automation_shopify_order_lookup_failed",
            extra={"organization_id": str(organization_id), "code": getattr(exc, "code", None)},
        )
        return False, "shopify_lookup_failed"

    if order is None:
        return False, "order_not_found"
    name = str(order.get("name", "") or order_number)
    status = str(order.get("displayFulfillmentStatus") or "unknown")
    return True, f"Order {name} (fulfillment: {status})"


async def read_shopify_catalog_titles(
    db: AsyncSession, organization_id: UUID, *, query: str, max_results: int
) -> tuple[bool, str]:
    try:
        _installation, connection = await connected_shopify_connection(db, organization_id)
        ref = connection_ref(connection)
    except LookupError:
        return False, "shopify_not_connected"

    adapter = ShopifyProductCatalogAdapter(resolve_shopify_credentials)
    try:
        page = await adapter.search_products(ref, query=query, limit=min(max(1, max_results), 10), cursor=None)
    except (ShopifyAPIError, ValueError) as exc:
        logger.warning(
            "automation_shopify_catalog_search_failed",
            extra={"organization_id": str(organization_id), "error": type(exc).__name__},
        )
        return False, "catalog_search_failed"

    titles = [p.title for p in page.items[:max_results] if p.title]
    if not titles:
        return True, "No matching products (verify sync and query)."
    return True, "Matches: " + "; ".join(titles)


async def ticket_customer_email(db: AsyncSession, organization_id: UUID, ticket_id: UUID) -> str | None:
    row = await db.scalar(
        select(Customer.email)
        .select_from(Ticket)
        .join(
            Customer,
            (Customer.organization_id == Ticket.organization_id) & (Customer.id == Ticket.customer_id),
        )
        .where(Ticket.organization_id == organization_id, Ticket.id == ticket_id)
    )
    email = row
    return email.strip() if isinstance(email, str) and email.strip() else None
