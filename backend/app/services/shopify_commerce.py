"""Application workflows for Shopify commerce reads exposed by existing APIs."""

import logging

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import set_tenant_context
from app.integrations.core.interfaces import CommerceCapability
from app.integrations.core.registry import IntegrationRegistry
from app.integrations.core.types import IntegrationCapability
from app.integrations.providers.shopify.client import ShopifyAPIError, log_shopify_api_event
from app.models import ShopifyAccessAudit, User
from app.schemas.shopify import ShopifyOrderPageOut, ShopifyOrderSummaryOut
from app.services.catalog import connected_shopify_connection, connection_ref
from app.services.shopify_errors import to_api_error
from app.services.shopify_order_lookup import shopify_query_fingerprint


async def list_shopify_order_page(
    *,
    db: AsyncSession,
    user: User,
    limit: int,
    cursor: str | None,
    registry: IntegrationRegistry,
) -> ShopifyOrderPageOut:
    """Use the registered commerce capability and audit a tenant's order page view."""
    installation, connection = await connected_shopify_connection(db, user.organization_id)
    await db.commit()
    await set_tenant_context(db, user.organization_id)
    capability = registry.get_capability(
        "shopify", IntegrationCapability.COMMERCE, CommerceCapability
    )

    try:
        page = await capability.list_orders(
            connection_ref(connection),
            limit=limit,
            cursor=cursor,
        )
    except ShopifyAPIError as exc:
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
            granted_scopes=sorted(installation.granted_scopes or []),
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

    items = [ShopifyOrderSummaryOut.model_validate(item) for item in page["items"]]
    db.add(
        ShopifyAccessAudit(
            organization_id=user.organization_id,
            user_id=user.id,
            resource_type="orders_list",
            result_count=len(items),
            query_fingerprint=shopify_query_fingerprint(
                installation.shop_domain,
                f"user:{user.id}",
                cursor or "first-page",
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
        has_next_page=page["has_next_page"],
    )
    return ShopifyOrderPageOut(
        items=items,
        has_next_page=page["has_next_page"],
        next_cursor=page["next_cursor"],
    )
