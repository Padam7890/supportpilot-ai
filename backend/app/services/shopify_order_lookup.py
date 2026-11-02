"""Application services for verified Shopify order retrieval and API mapping."""

import hashlib
import hmac
import re
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import set_tenant_context
from app.integrations.providers.shopify.client import ShopifyAPIError, fetch_orders
from app.integrations.providers.shopify.orders import lookup_authorized_order
from app.models import ShopifyAccessAudit, User
from app.schemas.shopify import (
    ShopifyCustomerOut,
    ShopifyOrderLookupOut,
    ShopifyOrderOut,
    ShopifyOrderSummaryOut,
    ShopifyTrackingOut,
)
from app.services.shopify_access import installation_for
from app.services.shopify_errors import to_api_error
from app.services.shopify_tokens import valid_access_token

ORDER_NUMBER = re.compile(r"^#?[A-Za-z0-9-]+$")


def shopify_search_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def shopify_query_fingerprint(shop_domain: str, customer_email: str, order_number: str) -> str:
    query = f"{shop_domain}\0{customer_email.strip().casefold()}\0{order_number.strip().casefold()}"
    return hmac.new(settings.jwt_secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def map_order(order: dict) -> ShopifyOrderOut:
    price = (order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
    tracking = []
    for fulfillment in order.get("fulfillments") or []:
        if not isinstance(fulfillment, dict):
            continue
        for info in fulfillment.get("trackingInfo") or []:
            if isinstance(info, dict):
                tracking.append(
                    ShopifyTrackingOut(
                        company=info.get("company"), number=info.get("number"), url=info.get("url")
                    )
                )
    return ShopifyOrderOut(
        id=str(order.get("id", "")),
        order_number=str(order.get("name", "")),
        created_at=order["createdAt"],
        financial_status=order.get("displayFinancialStatus"),
        fulfillment_status=order.get("displayFulfillmentStatus"),
        total_amount=str(price.get("amount", "")),
        currency=str(price.get("currencyCode", "")),
        tracking=tracking,
        cancelled_at=order.get("cancelledAt"),
        closed=order.get("closed"),
        return_status=order.get("returnStatus"),
    )


def map_order_summary(order: dict) -> ShopifyOrderSummaryOut:
    price = (order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
    return ShopifyOrderSummaryOut(
        id=str(order.get("id", "")),
        order_number=str(order.get("name", "")),
        created_at=order["createdAt"],
        financial_status=order.get("displayFinancialStatus"),
        fulfillment_status=order.get("displayFulfillmentStatus"),
        total_amount=str(price.get("amount", "")),
        currency=str(price.get("currencyCode", "")),
    )


async def verified_lookup(
    *,
    db: AsyncSession,
    user: User,
    customer_email: str,
    order_number: str,
    limit: int,
    cursor: str | None,
) -> ShopifyOrderLookupOut:
    installation = await installation_for(db, user.organization_id)
    normalized_email = customer_email.strip().lower()
    normalized_order = order_number.strip()
    fingerprint = shopify_query_fingerprint(
        installation.shop_domain, normalized_email, normalized_order
    )
    audit = ShopifyAccessAudit(
        organization_id=user.organization_id,
        user_id=user.id,
        resource_type="orders",
        result_count=0,
        query_fingerprint=fingerprint,
        details={"shop_domain": installation.shop_domain, "verification": "pending"},
    )
    db.add(audit)

    async def persist_audit() -> None:
        await db.commit()
        await set_tenant_context(db, user.organization_id)

    if not ORDER_NUMBER.fullmatch(normalized_order):
        audit.details = {
            "shop_domain": installation.shop_domain,
            "verification": "invalid_order_number",
        }
        await persist_audit()
        raise HTTPException(status_code=422, detail="Enter a valid Shopify order number")

    try:
        access_token = await valid_access_token(db, installation)
    except ShopifyAPIError as exc:
        audit.details = {
            "shop_domain": installation.shop_domain,
            "verification": "credential_error",
        }
        await persist_audit()
        raise to_api_error(exc) from exc
    except RuntimeError as exc:
        audit.details = {
            "shop_domain": installation.shop_domain,
            "verification": "credential_error",
        }
        await persist_audit()
        raise HTTPException(
            status_code=503, detail="Shopify credentials cannot be accessed"
        ) from exc
    except HTTPException:
        audit.details = {
            "shop_domain": installation.shop_domain,
            "verification": "credential_error",
        }
        await persist_audit()
        raise

    if not normalized_order.startswith("#"):
        normalized_order = f"#{normalized_order}"
    try:
        matched = await lookup_authorized_order(
            shop_domain=installation.shop_domain,
            access_token=access_token,
            order_number=normalized_order,
            customer_email=normalized_email,
        )
        if matched is None:
            audit.details = {
                "shop_domain": installation.shop_domain,
                "verification": "not_verified",
            }
            await persist_audit()
            raise HTTPException(
                status_code=404, detail="No order matched both the order number and customer email"
            )
        history = await fetch_orders(
            installation.shop_domain,
            access_token,
            search_query=f"email:{shopify_search_value(normalized_email)}",
            limit=limit,
            cursor=cursor,
        )
    except ShopifyAPIError as exc:
        audit.details = {"shop_domain": installation.shop_domain, "verification": "provider_error"}
        if exc.code == "shopify_reauthorization_required":
            installation.disconnected_at = datetime.now(UTC)
            installation.access_token_encrypted = None
            installation.refresh_token_encrypted = None
        await persist_audit()
        raise to_api_error(exc) from exc

    matching_history = [
        item
        for item in history["nodes"]
        if isinstance(item, dict)
        and isinstance(item.get("customer"), dict)
        and isinstance(item["customer"].get("email"), str)
        and item["customer"]["email"].casefold() == normalized_email.casefold()
    ]
    customer = matched.get("customer") or {}
    if (
        not isinstance(customer, dict)
        or customer.get("email", "").casefold() != normalized_email.casefold()
    ):
        audit.details = {"shop_domain": installation.shop_domain, "verification": "not_verified"}
        await persist_audit()
        raise HTTPException(
            status_code=404, detail="No order matched both the order number and customer email"
        )
    audit.result_count = len(matching_history) + 1
    audit.details = {
        "shop_domain": installation.shop_domain,
        "verification": "order_number_and_email",
    }
    return ShopifyOrderLookupOut(
        customer=ShopifyCustomerOut(
            display_name=customer.get("displayName"),
            email=normalized_email,
            verified_by="order_number_and_email",
        ),
        matched_order=map_order(matched),
        recent_orders=[map_order(item) for item in matching_history],
        has_next_page=bool(history["page_info"].get("hasNextPage")),
        next_cursor=history["page_info"].get("endCursor"),
    )
