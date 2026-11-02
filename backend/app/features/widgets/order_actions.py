"""Secure widget order verification and human-approved cancellation request endpoints."""

"""Public, narrowly scoped Shopify storefront chat and tenant widget settings."""

import hmac
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db, set_tenant_context
from app.integrations.providers.shopify.client import ShopifyAPIError
from app.integrations.providers.shopify.orders import lookup_authorized_order
from app.integrations.providers.shopify.security import decrypt_credential, encrypt_credential
from app.models import (
    Conversation,
    Message,
    WidgetOrderVerification,
)
from app.schemas.widget import (
    WidgetOrderVerificationCode,
    WidgetOrderVerificationOut,
    WidgetOrderVerificationStart,
)
from app.services.email_delivery import send_order_verification_code, smtp_is_configured
from app.services.shopify_access import installation_for
from app.services.shopify_order_lookup import map_order
from app.services.shopify_tokens import valid_access_token
from app.services.widget_ai import format_verified_order_status

logger = logging.getLogger(__name__)
VISITOR_SESSION_TTL = timedelta(hours=24)
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
MAX_HISTORY = 100

router = APIRouter(prefix="/widget", tags=["Public storefront chat"])
from app.features.widgets.shared import (
    _log_order_verification,
    _verification_digest,
    require_visitor_conversation,
)


@router.post(
    "/conversations/{conversation_id}/order-verification",
    response_model=WidgetOrderVerificationOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_widget_order_verification(
    conversation_id: UUID,
    payload: WidgetOrderVerificationStart,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> WidgetOrderVerificationOut:
    _log_order_verification(
        logging.INFO,
        "request_received",
        conversation_id=str(conversation_id),
    )
    try:
        widget, conversation, _ticket = await require_visitor_conversation(
            request, conversation_id, authorization, db
        )
    except HTTPException as exc:
        _log_order_verification(
            logging.WARNING,
            "request_rejected",
            conversation_id=str(conversation_id),
            http_status=exc.status_code,
            reason="visitor_authorization_or_origin_rejected",
        )
        raise
    if not widget.ai_enabled:
        _log_order_verification(
            logging.INFO,
            "request_blocked",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            reason="widget_ai_disabled",
        )
        raise HTTPException(status_code=409, detail="AI support is not enabled for this store")
    if not payload.consent:
        _log_order_verification(
            logging.INFO,
            "request_blocked",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            reason="consent_missing",
        )
        raise HTTPException(
            status_code=422, detail="Consent is required to verify an order by email"
        )
    if not smtp_is_configured():
        _log_order_verification(
            logging.ERROR,
            "email_blocked",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            reason="smtp_not_configured",
        )
        raise HTTPException(status_code=503, detail="Order verification email is not configured")

    _log_order_verification(
        logging.INFO,
        "request_started",
        organization_id=str(widget.organization_id),
        conversation_id=str(conversation.id),
    )

    now = datetime.now(UTC)
    locked_conversation = await db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation.id,
            Conversation.organization_id == widget.organization_id,
        )
        .with_for_update()
    )
    if locked_conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    recent_requests = await db.scalar(
        select(func.count(WidgetOrderVerification.id)).where(
            WidgetOrderVerification.organization_id == widget.organization_id,
            WidgetOrderVerification.conversation_id == conversation.id,
            WidgetOrderVerification.created_at >= now - timedelta(minutes=10),
        )
    )
    if (recent_requests or 0) >= 3:
        _log_order_verification(
            logging.WARNING,
            "request_rate_limited",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            request_count=recent_requests or 0,
        )
        raise HTTPException(
            status_code=429, detail="Too many verification requests. Try again later."
        )

    try:
        installation = await installation_for(db, widget.organization_id)
        token = await valid_access_token(db, installation)
        order = await lookup_authorized_order(
            shop_domain=installation.shop_domain,
            access_token=token,
            order_number=payload.order_number,
            customer_email=str(payload.email).strip().casefold(),
        )
    except ShopifyAPIError as exc:
        _log_order_verification(
            logging.WARNING,
            "shopify_lookup_failed",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            provider_status_code=exc.status_code,
            error_code=exc.code,
        )
        raise HTTPException(
            status_code=503, detail="Shopify order lookup is temporarily unavailable"
        ) from exc
    if order is None:
        # Do not reveal whether an email or order number exists in the store.
        _log_order_verification(
            logging.INFO,
            "no_shopify_match",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
        )
        return WidgetOrderVerificationOut(
            message="If the details match a recent order, a verification code has been sent to its checkout email."
        )

    pending = list(
        await db.scalars(
            select(WidgetOrderVerification)
            .where(
                WidgetOrderVerification.organization_id == widget.organization_id,
                WidgetOrderVerification.conversation_id == conversation.id,
                WidgetOrderVerification.status.in_(("pending", "verified")),
            )
            .with_for_update()
        )
    )
    for previous in pending:
        previous.status = "expired"

    verification_id = uuid4()
    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        encrypted_email = encrypt_credential(str(payload.email).strip().casefold())
    except RuntimeError as exc:
        _log_order_verification(
            logging.ERROR,
            "email_address_encryption_failed",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            error_type=type(exc).__name__,
        )
        raise HTTPException(status_code=503, detail="Order verification is not configured") from exc
    verification = WidgetOrderVerification(
        id=verification_id,
        organization_id=widget.organization_id,
        widget_id=widget.id,
        conversation_id=conversation.id,
        order_number=str(order.get("name", payload.order_number)),
        shopify_order_id=str(order.get("id", "")),
        customer_email_encrypted=encrypted_email,
        code_digest=_verification_digest(verification_id, code),
        status="pending",
        attempt_count=0,
        expires_at=now + timedelta(minutes=10),
        consented_at=now,
        created_at=now,
    )
    db.add(verification)
    await db.commit()
    _log_order_verification(
        logging.INFO,
        "verification_created",
        organization_id=str(widget.organization_id),
        conversation_id=str(conversation.id),
        verification_id=str(verification_id),
        expires_in_seconds=600,
    )
    try:
        await send_order_verification_code(str(payload.email), code)
    except Exception as exc:  # SMTP errors must not leak addresses or provider details.
        # COMMIT clears PostgreSQL's transaction-local tenant setting. Restore it
        # before updating this row so RLS doesn't silently match zero rows.
        await set_tenant_context(db, widget.organization_id)
        verification.status = "expired"
        await db.commit()
        _log_order_verification(
            logging.ERROR,
            "email_failed",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            verification_id=str(verification_id),
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503, detail="Could not send the verification email"
        ) from exc
    _log_order_verification(
        logging.INFO,
        "email_sent",
        organization_id=str(widget.organization_id),
        conversation_id=str(conversation.id),
        verification_id=str(verification_id),
    )
    return WidgetOrderVerificationOut(
        message="If the details match a recent order, a verification code has been sent to its checkout email."
    )


@router.post(
    "/conversations/{conversation_id}/order-verification/confirm",
    response_model=WidgetOrderVerificationOut,
)
async def confirm_widget_order_verification(
    conversation_id: UUID,
    payload: WidgetOrderVerificationCode,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> WidgetOrderVerificationOut:
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
            WidgetOrderVerification.status == "pending",
        )
        .order_by(WidgetOrderVerification.created_at.desc())
        .with_for_update()
    )
    if verification is None or verification.expires_at <= now:
        if verification is not None:
            verification.status = "expired"
            await db.commit()
        _log_order_verification(
            logging.WARNING,
            "code_rejected",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            reason="missing_or_expired",
        )
        raise HTTPException(
            status_code=400, detail="Code is invalid or expired. Request a new code."
        )
    supplied = _verification_digest(verification.id, payload.code)
    if not hmac.compare_digest(verification.code_digest, supplied):
        verification.attempt_count += 1
        if verification.attempt_count >= 5:
            verification.status = "locked"
        await db.commit()
        _log_order_verification(
            logging.WARNING,
            "code_rejected",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            verification_id=str(verification.id),
            attempt_count=verification.attempt_count,
            locked=verification.status == "locked",
            reason="invalid_code",
        )
        raise HTTPException(
            status_code=400, detail="Code is invalid or expired. Request a new code."
        )

    try:
        email = decrypt_credential(verification.customer_email_encrypted)
        installation = await installation_for(db, widget.organization_id)
        token = await valid_access_token(db, installation)
        order = await lookup_authorized_order(
            shop_domain=installation.shop_domain,
            access_token=token,
            order_number=verification.order_number,
            customer_email=email,
        )
    except (RuntimeError, ShopifyAPIError) as exc:
        _log_order_verification(
            logging.WARNING,
            "confirm_lookup_failed",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            verification_id=str(verification.id),
            error_type=type(exc).__name__,
            provider_status_code=exc.status_code if isinstance(exc, ShopifyAPIError) else None,
            error_code=exc.code if isinstance(exc, ShopifyAPIError) else "credential_error",
        )
        raise HTTPException(
            status_code=503, detail="Shopify order lookup is temporarily unavailable"
        ) from exc
    if order is None or order.get("id") != verification.shopify_order_id:
        verification.status = "expired"
        await db.commit()
        _log_order_verification(
            logging.WARNING,
            "confirm_order_changed",
            organization_id=str(widget.organization_id),
            conversation_id=str(conversation.id),
            verification_id=str(verification.id),
        )
        raise HTTPException(
            status_code=409, detail="Order details changed. Please verify the order again."
        )

    mapped = map_order(order)
    answer = format_verified_order_status(mapped, opening="I verified order")
    verification.status = "verified"
    verification.verified_at = now
    if widget.ai_reply_mode == "auto_reply":
        db.add(
            Message(
                organization_id=widget.organization_id,
                conversation_id=conversation.id,
                sender_type="assistant",
                sender_user_id=None,
                content=answer,
                content_type="text",
            )
        )
        conversation.updated_at = now
        ticket.updated_at = now
    else:
        private_summary = answer
        if mapped.financial_status:
            private_summary += (
                f" Financial status: {mapped.financial_status.replace('_', ' ').lower()}."
            )
        db.add(
            Message(
                organization_id=widget.organization_id,
                conversation_id=conversation.id,
                sender_type="internal_note",
                sender_user_id=None,
                content=f"Shopper verified order {mapped.order_number}. Private order lookup: {private_summary}",
                content_type="text",
            )
        )
        conversation.updated_at = now
        ticket.updated_at = now
    await db.commit()
    _log_order_verification(
        logging.INFO,
        "verification_succeeded",
        organization_id=str(widget.organization_id),
        conversation_id=str(conversation.id),
        verification_id=str(verification.id),
        delivery_mode=widget.ai_reply_mode,
    )
    if widget.ai_reply_mode != "auto_reply":
        return WidgetOrderVerificationOut(
            message="Your order is verified. A support teammate will follow up here shortly.",
            verified=True,
        )
    return WidgetOrderVerificationOut(
        message=answer,
        verified=True,
        order_number=mapped.order_number,
        financial_status=mapped.financial_status,
        fulfillment_status=mapped.fulfillment_status,
        tracking=[item.model_dump() for item in mapped.tracking],
    )



