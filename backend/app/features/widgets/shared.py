"""Shared validation and session helpers for the storefront widget feature."""

"""Public, narrowly scoped Shopify storefront chat and tenant widget settings."""

import hashlib
import hmac
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import limit_auth_attempts
from app.core.config import settings
from app.core.security import create_widget_visitor_token, decode_widget_visitor_token
from app.db.session import set_tenant_context
from app.models import (
    Conversation,
    Message,
    Organization,
    SupportWidget,
    Ticket,
    WidgetSubmission,
)
from app.schemas.recommendations import ProductComparisonResult, RecommendationResult
from app.schemas.widget import (
    WidgetConfigOut,
    WidgetFirstMessage,
    WidgetMessageOut,
    WidgetStartOut,
)

logger = logging.getLogger(__name__)
VISITOR_SESSION_TTL = timedelta(hours=24)
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
MAX_HISTORY = 100
def _log_order_verification(level: int, event: str, **fields: object) -> None:
    """Emit structured diagnostics in the message so default console logs show them.

    Never pass customer email, order number, OTP, visitor token, or provider payloads.
    """
    logger.log(
        level,
        "widget_order_verification %s",
        json.dumps({"event": event, **fields}, sort_keys=True),
    )


def widget_message_out(message: Message) -> WidgetMessageOut:
    raw = message.provider_metadata.get("recommendation") if message.provider_metadata else None
    recommendation = None
    if isinstance(raw, dict):
        try:
            recommendation = (
                RecommendationResult.model_validate(raw)
                if "suggested_follow_ups" in raw
                or raw.get("response_type") in {"recommendations", "no_match", "unsupported"}
                else ProductComparisonResult.model_validate(raw)
            )
        except ValueError:
            logger.warning(
                "Widget recommendation payload failed schema validation: message_id=%s", message.id
            )
    return WidgetMessageOut(
        id=message.id,
        sender_type=message.sender_type,
        content=message.content,
        created_at=message.created_at,
        recommendation=recommendation,
    )


def normalize_origin(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme not in {"https", "http"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Enter an origin such as https://store.example")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Storefront origins must use HTTPS")
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Storefront origin has an invalid port") from exc
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if port and not (
        (parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80)
    ):
        host = f"{host}:{port}"
    return f"{parsed.scheme}://{host}"


def normalized_origins(values: list[str]) -> list[str]:
    try:
        return sorted({normalize_origin(value) for value in values})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def widget_out(
    widget: SupportWidget,
    ai_agent_ids: list[UUID] | None = None,
    last_customer_message_at: datetime | None = None,
) -> WidgetConfigOut:
    return WidgetConfigOut(
        public_id=widget.public_id,
        ai_agent_id=widget.ai_agent_id,
        ai_agent_ids=ai_agent_ids or [widget.ai_agent_id],
        allowed_origins=widget.allowed_origins,
        enabled=widget.enabled,
        collect_contact=widget.collect_contact,
        ai_enabled=widget.ai_enabled,
        ai_reply_mode=widget.ai_reply_mode,
        last_widget_load_at=widget.last_widget_load_at,
        last_customer_message_at=last_customer_message_at,
        created_at=widget.created_at,
    )


async def require_allowed_widget_origin(
    request: Request, public_id: str, db: AsyncSession
) -> tuple[SupportWidget, Organization]:
    origin_header = request.headers.get("origin")
    if not origin_header:
        raise HTTPException(status_code=403, detail="Storefront origin is required")
    try:
        origin = normalize_origin(origin_header)
    except ValueError:
        raise HTTPException(status_code=403, detail="Storefront origin is not allowed") from None

    widget = await db.scalar(
        select(SupportWidget).where(
            SupportWidget.public_id == public_id,
            SupportWidget.enabled.is_(True),
        )
    )
    if widget is None or origin not in set(widget.allowed_origins or []):
        raise HTTPException(status_code=403, detail="Storefront origin is not allowed")

    await set_tenant_context(db, widget.organization_id)
    organization = await db.scalar(
        select(Organization).where(
            Organization.id == widget.organization_id,
            Organization.approval_status == "approved",
        )
    )
    if organization is None:
        raise HTTPException(status_code=404, detail="Widget is unavailable")
    return widget, organization


async def rate_limit_widget(request: Request, public_id: str) -> None:
    ip = request.client.host if request.client else "unknown"
    await limit_auth_attempts(
        request,
        f"widget:{public_id}:{ip}",
        limit=20,
        window_seconds=60,
    )


def request_hash(payload: WidgetFirstMessage) -> str:
    canonical = json.dumps(
        {
            "content": payload.content,
            "visitor_name": payload.visitor_name,
            "visitor_email": str(payload.visitor_email).casefold()
            if payload.visitor_email
            else None,
            "contact_consent": payload.contact_consent,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(settings.jwt_secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def make_start_response(submission: WidgetSubmission, widget: SupportWidget) -> WidgetStartOut:
    if submission.ticket_id is None or submission.conversation_id is None:
        raise HTTPException(status_code=503, detail="The conversation is still being created")
    if submission.visitor_token_expires_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=410, detail="This visitor session expired. Start a new chat."
        )
    token = create_widget_visitor_token(
        organization_id=str(submission.organization_id),
        widget_public_id=widget.public_id,
        conversation_id=str(submission.conversation_id),
        expires_at=submission.visitor_token_expires_at,
    )
    return WidgetStartOut(
        ticket_id=submission.ticket_id,
        conversation_id=submission.conversation_id,
        visitor_token=token,
        visitor_token_expires_at=submission.visitor_token_expires_at,
        confirmation="Thanks for contacting us. A teammate will reply here as soon as possible.",
    )


async def require_visitor_conversation(
    request: Request,
    conversation_id: UUID,
    authorization: str | None,
    db: AsyncSession,
) -> tuple[SupportWidget, Conversation, Ticket]:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Visitor session is required")
    try:
        claims = decode_widget_visitor_token(authorization[7:].strip())
        token_conversation_id = UUID(claims.get("sub", ""))
        organization_id = UUID(claims.get("org", ""))
        public_id = claims.get("wid")
    except (jwt.InvalidTokenError, TypeError, ValueError):
        raise HTTPException(
            status_code=401, detail="Visitor session is invalid or expired"
        ) from None
    if token_conversation_id != conversation_id or not isinstance(public_id, str):
        raise HTTPException(
            status_code=403, detail="Visitor session cannot access this conversation"
        )

    widget, _organization = await require_allowed_widget_origin(request, public_id, db)
    if widget.organization_id != organization_id:
        raise HTTPException(
            status_code=403, detail="Visitor session cannot access this conversation"
        )
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == organization_id,
            Conversation.channel == "shopify_widget",
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    ticket = await db.scalar(
        select(Ticket).where(
            Ticket.id == conversation.ticket_id,
            Ticket.organization_id == organization_id,
            Ticket.source == "shopify_widget",
        )
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await rate_limit_widget(request, public_id)
    return widget, conversation, ticket


def _verification_digest(verification_id: UUID, code: str) -> str:
    return hmac.new(
        settings.jwt_secret.encode(),
        f"{verification_id}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()

