"""Create verified, human-reviewed Shopify cancellation requests from automation."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.automations.shopify_actions import extract_order_number
from app.integrations.providers.shopify.actions import (
    ShopifyOrderActionError,
    check_cancellation_eligibility,
    check_cancellation_scope,
)
from app.integrations.providers.shopify.client import ShopifyAPIError
from app.integrations.providers.shopify.orders import lookup_authorized_order
from app.integrations.providers.shopify.security import decrypt_credential
from app.models import (
    CommerceAction,
    CommerceActionAudit,
    Conversation,
    Ticket,
    WidgetOrderVerification,
)
from app.schemas.commerce_action import CommerceActionCreate
from app.services.commerce_action_identity import (
    commerce_action_fingerprint,
    commerce_idempotency_hash,
)
from app.services.catalog import (
    connected_shopify_connection,
    connection_ref,
)
from app.services.shopify_commerce_credentials import resolve_shopify_commerce_credentials

logger = logging.getLogger(__name__)
ACTION_TTL = timedelta(days=7)


async def request_verified_shopify_cancellation(
    db: AsyncSession,
    organization_id: UUID,
    *,
    ticket_id: UUID,
    conversation_id: UUID,
    summary: str,
    detail: str | None,
    order_number_regex: str,
    message: str,
    execution_id: UUID,
    action_index: int,
) -> tuple[str, str, UUID | None]:
    """Queue a cancellation review only for an OTP-verified order in this conversation."""
    ticket = await db.scalar(
        select(Ticket)
        .join(
            Conversation,
            (Conversation.organization_id == Ticket.organization_id)
            & (Conversation.ticket_id == Ticket.id)
            & (Conversation.id == conversation_id),
        )
        .where(Ticket.organization_id == organization_id, Ticket.id == ticket_id)
    )
    if ticket is None:
        return "skipped", "Ticket not found", None
    order_number = extract_order_number(message, order_number_regex)
    if not order_number:
        return "skipped", "No order number was found; a teammate must review the request", None

    verification = await db.scalar(
        select(WidgetOrderVerification)
        .where(
            WidgetOrderVerification.organization_id == organization_id,
            WidgetOrderVerification.conversation_id == conversation_id,
            WidgetOrderVerification.status == "verified",
            WidgetOrderVerification.expires_at > datetime.now(UTC),
        )
        .order_by(WidgetOrderVerification.verified_at.desc())
        .limit(1)
    )
    if verification is None:
        return "skipped", "The shopper must verify this order by email before cancellation review", None
    if order_number.casefold().lstrip("#") != verification.order_number.casefold().lstrip("#"):
        return "skipped", "The requested order differs from the verified order; verify it before review", None

    try:
        installation, connection = await connected_shopify_connection(db, organization_id)
    except LookupError:
        return "skipped", "Shopify is not connected; a teammate must review the request", None

    try:
        check_cancellation_scope(installation.granted_scopes or [])
    except ShopifyOrderActionError:
        return "skipped", "Shopify cancellation permission is unavailable", None

    try:
        shop_domain, access_token, _scopes = await resolve_shopify_commerce_credentials(
            connection_ref(connection)
        )
        verified_email = decrypt_credential(verification.customer_email_encrypted)
        order = await lookup_authorized_order(
            shop_domain=shop_domain,
            access_token=access_token,
            order_number=verification.order_number,
            customer_email=verified_email,
        )
    except (HTTPException, ShopifyAPIError, RuntimeError) as exc:
        logger.warning(
            "automation_shopify_cancellation_verification_failed",
            extra={
                "organization_id": str(organization_id),
                "connection_id": str(connection.id),
                "error_type": type(exc).__name__,
            },
        )
        return "skipped", "Shopify could not verify this order; a teammate must review it", None

    if order is None or order.get("id") != verification.shopify_order_id:
        return "skipped", "Shopify could not match this order to the ticket customer", None
    try:
        check_cancellation_eligibility(order)
    except ShopifyOrderActionError as exc:
        return "skipped", f"The verified order cannot be cancelled ({exc.code})", None

    price_set = order.get("currentTotalPriceSet")
    shop_money = price_set.get("shopMoney") if isinstance(price_set, dict) else None
    amount = shop_money.get("amount") if isinstance(shop_money, dict) else None
    currency = shop_money.get("currencyCode") if isinstance(shop_money, dict) else None
    try:
        order_total = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return "skipped", "Shopify returned incomplete order totals; a teammate must review it", None
    if not order_total.is_finite() or not isinstance(currency, str) or len(currency) != 3:
        return "skipped", "Shopify returned incomplete order totals; a teammate must review it", None

    verified_order_number = order.get("name")
    shopify_order_id = order.get("id")
    if not isinstance(verified_order_number, str) or not isinstance(shopify_order_id, str):
        return "skipped", "Shopify returned incomplete order identity; a teammate must review it", None

    request_reason = f"[Automation] {summary.strip()}"[:500]
    payload = CommerceActionCreate(
        ticket_id=ticket_id,
        order_number=verified_order_number,
        action_type="cancel",
        provider="shopify",
        reason=request_reason,
    )
    idempotency_key = f"automation-exec:{execution_id}:commerce:{action_index}"
    key_digest = commerce_idempotency_hash(idempotency_key)
    request_digest = commerce_action_fingerprint(payload)
    existing = await db.scalar(
        select(CommerceAction).where(
            CommerceAction.organization_id == organization_id,
            CommerceAction.idempotency_key_hash == key_digest,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != request_digest:
            raise RuntimeError("automation_commerce_idempotency_conflict")
        return "skipped", "Cancellation review already exists for this workflow run", existing.id

    action = CommerceAction(
        organization_id=organization_id,
        ticket_id=ticket_id,
        requested_by_user_id=None,
        action_type="cancel",
        provider="shopify",
        shopify_order_id=shopify_order_id,
        order_number=verified_order_number,
        order_total=order_total,
        currency=currency.upper(),
        refund_amount=None,
        cancel_refund=False,
        cancel_restock=False,
        cancel_notify_customer=False,
        cancellation_reason="CUSTOMER",
        reason=request_reason,
        idempotency_key_hash=key_digest,
        request_fingerprint=request_digest,
        approval_status="pending",
        expires_at=datetime.now(UTC) + ACTION_TTL,
        execution_status="not_started",
    )
    db.add(action)
    await db.flush()
    db.add(
        CommerceActionAudit(
            organization_id=organization_id,
            commerce_action_id=action.id,
            actor_user_id=None,
            event_type="requested",
            details={
                "source": "automation",
                "execution_id": str(execution_id),
                "summary": summary.strip()[:200],
            },
        )
    )
    logger.info(
        "automation_verified_cancellation_review_created",
        extra={
            "organization_id": str(organization_id),
            "ticket_id": str(ticket_id),
            "commerce_action_id": str(action.id),
            "execution_id": str(execution_id),
            "shopify_connection_id": str(connection.id),
        },
    )
    return "applied", detail.strip() if detail and detail.strip() else "A verified cancellation request is waiting for human review", action.id
