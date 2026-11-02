"""Secure widget order verification and human-approved cancellation request endpoints."""

"""Public, narrowly scoped Shopify storefront chat and tenant widget settings."""

import hashlib
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db, set_tenant_context
from app.features.widgets.shared import require_visitor_conversation
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
    Message,
    WidgetOrderVerification,
)
from app.schemas.widget import (
    WidgetCancellationRequest,
    WidgetOrderVerificationOut,
)
from app.services.shopify_access import installation_for
from app.services.shopify_tokens import valid_access_token

logger = logging.getLogger(__name__)
VISITOR_SESSION_TTL = timedelta(hours=24)
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
MAX_HISTORY = 100

router = APIRouter(prefix="/widget", tags=["Public storefront chat"])
@router.post(
    "/conversations/{conversation_id}/cancellation-request",
    response_model=WidgetOrderVerificationOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_widget_order_cancellation(
    conversation_id: UUID,
    payload: WidgetCancellationRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> WidgetOrderVerificationOut:
    if not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="A valid idempotency key is required")
    widget, conversation, ticket = await require_visitor_conversation(
        request, conversation_id, authorization, db
    )
    now = datetime.now(UTC)
    verification = await db.scalar(
        select(WidgetOrderVerification)
        .where(
            WidgetOrderVerification.organization_id == widget.organization_id,
            WidgetOrderVerification.widget_id == widget.id,
            WidgetOrderVerification.conversation_id == conversation.id,
            WidgetOrderVerification.status == "verified",
            WidgetOrderVerification.expires_at > now,
        )
        .order_by(WidgetOrderVerification.verified_at.desc())
        .with_for_update()
    )
    if verification is None:
        raise HTTPException(
            status_code=403, detail="Verify the order by email code before requesting cancellation"
        )

    key_digest = hashlib.sha256(
        f"widget-cancel:{conversation.id}:{idempotency_key.strip()}".encode()
    ).hexdigest()
    canonical = json.dumps(
        {
            "conversation_id": str(conversation.id),
            "order_id": verification.shopify_order_id,
            "reason": payload.reason,
            "action_type": "cancel",
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    request_fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    existing = await db.scalar(
        select(CommerceAction).where(
            CommerceAction.organization_id == widget.organization_id,
            CommerceAction.idempotency_key_hash == key_digest,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != request_fingerprint:
            raise HTTPException(
                status_code=409, detail="Idempotency-Key was already used for a different request"
            )
        return WidgetOrderVerificationOut(
            message="Your cancellation request is with the support team for review.",
            verified=True,
        )
    already_pending = await db.scalar(
        select(CommerceAction).where(
            CommerceAction.organization_id == widget.organization_id,
            CommerceAction.provider == "shopify",
            CommerceAction.action_type == "cancel",
            CommerceAction.shopify_order_id == verification.shopify_order_id,
            CommerceAction.approval_status == "pending",
        )
    )
    if already_pending is not None:
        return WidgetOrderVerificationOut(
            message="A cancellation request for this order is already with the support team for review.",
            verified=True,
        )

    try:
        installation = await installation_for(db, widget.organization_id)
        check_cancellation_scope(installation.granted_scopes)
        email = decrypt_credential(verification.customer_email_encrypted)
        token = await valid_access_token(db, installation)
        order = await lookup_authorized_order(
            shop_domain=installation.shop_domain,
            access_token=token,
            order_number=verification.order_number,
            customer_email=email,
        )
        if order is None or order.get("id") != verification.shopify_order_id:
            raise HTTPException(
                status_code=409, detail="Order could not be reverified. Please check its status."
            )
        check_cancellation_eligibility(order)
    except ShopifyOrderActionError as exc:
        details = {
            "shopify_cancel_permission_denied": "The store has not granted cancellation permission.",
            "shopify_order_already_cancelled": "This order has already been cancelled.",
            "shopify_order_not_cancelable": "This order can no longer be cancelled.",
            "shopify_order_has_active_return": "This order has an active return and cannot be cancelled.",
        }
        raise HTTPException(
            status_code=409, detail=details.get(exc.code, "This order cannot be cancelled.")
        ) from exc
    except ShopifyAPIError as exc:
        raise HTTPException(
            status_code=503, detail="Shopify order lookup is temporarily unavailable"
        ) from exc

    price = (order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
    try:
        order_total = Decimal(str(price.get("amount", "")))
    except (InvalidOperation, ValueError) as exc:
        raise HTTPException(
            status_code=502, detail="Shopify returned an invalid order total"
        ) from exc
    if order_total < 0:
        raise HTTPException(status_code=502, detail="Shopify returned an invalid order total")
    organization_id = widget.organization_id
    verified_order_id = verification.shopify_order_id

    action = CommerceAction(
        organization_id=widget.organization_id,
        ticket_id=ticket.id,
        requested_by_user_id=None,
        action_type="cancel",
        provider="shopify",
        shopify_order_id=verification.shopify_order_id,
        order_number=verification.order_number,
        order_total=order_total,
        currency=str(price.get("currencyCode", "USD"))[:3],
        refund_amount=None,
        cancel_refund=False,
        cancel_restock=False,
        cancel_notify_customer=False,
        cancellation_reason="CUSTOMER",
        reason=f"Customer requested cancellation: {payload.reason}"[:500],
        idempotency_key_hash=key_digest,
        request_fingerprint=request_fingerprint,
        approval_status="pending",
        expires_at=now + timedelta(days=7),
        execution_status="not_started",
    )
    db.add(action)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        await set_tenant_context(db, organization_id)
        canonical_action = await db.scalar(
            select(CommerceAction).where(
                CommerceAction.organization_id == organization_id,
                CommerceAction.provider == "shopify",
                CommerceAction.action_type == "cancel",
                CommerceAction.shopify_order_id == verified_order_id,
                CommerceAction.approval_status == "pending",
            )
        )
        if canonical_action is None:
            raise HTTPException(status_code=503, detail="Cancellation request could not be saved")
        return WidgetOrderVerificationOut(
            message="A cancellation request for this order is already with the support team for review.",
            verified=True,
        )
    db.add(
        CommerceActionAudit(
            organization_id=widget.organization_id,
            commerce_action_id=action.id,
            actor_user_id=None,
            event_type="requested",
            details={
                "source": "shopify_widget",
                "order_number": verification.order_number,
                "action_type": "cancel",
                "approval_required": True,
            },
        )
    )
    confirmation = "I sent your cancellation request to the support team. They must review it before any changes are made."
    db.add(
        Message(
            organization_id=widget.organization_id,
            conversation_id=conversation.id,
            sender_type="assistant",
            sender_user_id=None,
            content=confirmation,
            content_type="text",
        )
    )
    conversation.updated_at = now
    ticket.updated_at = now
    await db.commit()
    return WidgetOrderVerificationOut(message=confirmation, verified=True)

