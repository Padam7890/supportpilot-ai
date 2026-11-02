"""Shopify order APIs. Business verification and mapping live in application services."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db, set_tenant_context
from app.integrations.providers.shopify.client import (
    ShopifyAPIError,
    effective_shopify_scopes,
    fetch_order_page,
    log_shopify_api_event,
)
from app.integrations.providers.shopify.security import REQUIRED_SCOPES
from app.models import ShopifyAccessAudit, User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.shopify import (
    ShopifyOrderLookupOut,
    ShopifyOrderOut,
    ShopifyOrderPageOut,
)
from app.services.shopify_access import installation_for
from app.services.shopify_errors import to_api_error
from app.services.shopify_order_lookup import (
    map_order_summary,
    shopify_query_fingerprint,
    verified_lookup,
)
from app.services.shopify_tokens import valid_access_token

logger = logging.getLogger(__name__)
orders_router = APIRouter(
    prefix="/integrations/shopify", tags=["Shopify integration"], responses=COMMON_ERROR_RESPONSES
)


@orders_router.get("/orders/list", response_model=ShopifyOrderPageOut)
async def list_shopify_orders(
    limit: int = Query(default=25, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=512),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent", "viewer")),
) -> ShopifyOrderPageOut:
    """List a tenant's connected store orders without returning customer PII."""
    installation = await installation_for(db, user.organization_id)
    try:
        access_token = await valid_access_token(db, installation)
        page = await fetch_order_page(
            installation.shop_domain,
            access_token,
            limit=limit,
            cursor=cursor,
        )
    except ShopifyAPIError as exc:
        effective_scopes = effective_shopify_scopes(installation.granted_scopes)
        log_shopify_api_event(
            "orders_list_failed",
            level=logging.ERROR,
            organization_id=str(user.organization_id),
            user_id=str(user.id),
            shop_domain=installation.shop_domain,
            operation="SupportPilotOrderPage",
            error_code=exc.code,
            provider_error_code=exc.reason_code,
            provider_status_code=exc.status_code,
            granted_scopes=sorted(installation.granted_scopes),
            effective_scopes=sorted(effective_scopes),
            missing_required_scopes=sorted(set(REQUIRED_SCOPES) - effective_scopes),
        )
        raise to_api_error(exc) from exc
    except RuntimeError as exc:
        log_shopify_api_event(
            "orders_list_failed",
            level=logging.ERROR,
            organization_id=str(user.organization_id),
            user_id=str(user.id),
            shop_domain=installation.shop_domain,
            operation="SupportPilotOrderPage",
            error_code="shopify_credentials_unavailable",
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503, detail="Shopify credentials cannot be accessed"
        ) from exc

    items = [map_order_summary(item) for item in page["nodes"] if isinstance(item, dict)]
    cursor_fingerprint = cursor or "first-page"
    db.add(
        ShopifyAccessAudit(
            organization_id=user.organization_id,
            user_id=user.id,
            resource_type="orders_list",
            result_count=len(items),
            query_fingerprint=shopify_query_fingerprint(
                installation.shop_domain,
                f"user:{user.id}",
                cursor_fingerprint,
            ),
            details={"shop_domain": installation.shop_domain, "view": "orders_list"},
        )
    )
    await db.commit()
    await set_tenant_context(db, user.organization_id)
    log_shopify_api_event(
        "orders_list_succeeded",
        organization_id=str(user.organization_id),
        user_id=str(user.id),
        shop_domain=installation.shop_domain,
        operation="SupportPilotOrderPage",
        returned_count=len(items),
        has_next_page=bool(page["page_info"].get("hasNextPage")),
    )
    page_info = page["page_info"]
    return ShopifyOrderPageOut(
        items=items,
        has_next_page=bool(page_info.get("hasNextPage")),
        next_cursor=page_info.get("endCursor"),
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
