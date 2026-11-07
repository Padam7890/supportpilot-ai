"""Shopify order APIs. Business verification and mapping live in application services."""

from fastapi import APIRouter, Depends, Query, Request
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.integrations.core.registry import IntegrationRegistry
from app.models import User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.shopify import ShopifyOrderLookupOut, ShopifyOrderOut, ShopifyOrderPageOut
from app.services.shopify_commerce import list_shopify_order_page
from app.services.shopify_order_lookup import (
    verified_lookup,
)

orders_router = APIRouter(
    prefix="/integrations/shopify", tags=["Shopify integration"], responses=COMMON_ERROR_RESPONSES
)


@orders_router.get("/orders/list", response_model=ShopifyOrderPageOut)
async def list_shopify_orders(
    request: Request,
    limit: int = Query(default=25, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=512),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent", "viewer")),
) -> ShopifyOrderPageOut:
    """List a tenant's connected store orders without returning customer PII."""
    registry: IntegrationRegistry = request.app.state.integration_registry
    return await list_shopify_order_page(
        db=db,
        user=user,
        limit=limit,
        cursor=cursor,
        registry=registry,
    )


@orders_router.get("/orders", response_model=ShopifyOrderLookupOut)
async def lookup_shopify_orders(
    customer_email: EmailStr,
    order_number: str = Query(min_length=1, max_length=60, pattern=r"^#?[A-Za-z0-9-]+$"),
    limit: int = Query(default=10, ge=1, le=20),
    cursor: str | None = Query(default=None, max_length=512),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> ShopifyOrderLookupOut:
    # Shopify data is returned only after exact order-number AND customer-email verification.
    return await verified_lookup(
        db=db,
        user=user,
        customer_email=str(customer_email),
        order_number=order_number,
        limit=limit,
        cursor=cursor,
    )


@orders_router.get("/orders/{order_number}", response_model=ShopifyOrderOut)
async def get_verified_shopify_order(
    order_number: str,
    customer_email: EmailStr,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> ShopifyOrderOut:
    result = await verified_lookup(
        db=db,
        user=user,
        customer_email=str(customer_email),
        order_number=order_number,
        limit=1,
        cursor=None,
    )
    return result.matched_order
