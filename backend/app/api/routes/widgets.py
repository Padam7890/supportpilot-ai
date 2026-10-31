"""Public, narrowly scoped Shopify storefront chat and tenant widget settings."""

import hashlib
import hmac
import json
import re
import secrets
import string
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import limit_auth_attempts, require_roles
from app.core.config import settings
from app.core.security import create_widget_visitor_token, decode_widget_visitor_token
from app.db.session import get_db, set_tenant_context
from app.models import (
    Conversation,
    Customer,
    Message,
    Organization,
    SupportWidget,
    Ticket,
    TicketActivity,
    User,
    ShopifyAccessAudit,
    WidgetOrderVerification,
    WidgetSubmission,
)
from app.schemas.widget import (
    PublicWidgetConfigOut,
    WidgetConfigCreate,
    WidgetConfigOut,
    WidgetConfigUpdate,
    WidgetConversationOut,
    WidgetFirstMessage,
    WidgetMessageCreate,
    WidgetMessageOut,
    WidgetOrderVerificationCode,
    WidgetOrderVerificationOut,
    WidgetOrderVerificationStart,
    WidgetStartOut,
)
from app.services.widget_ai import enqueue_widget_reply
from app.api.routes.integrations import (
    installation_for,
    map_order,
    shopify_query_fingerprint,
    valid_access_token,
)
from app.services.email_delivery import send_order_verification_code, smtp_is_configured
from app.services.shopify_orders import lookup_authorized_order
from app.services.shopify_security import decrypt_credential, encrypt_credential

management_router = APIRouter(
    prefix="/integrations/widget", tags=["Storefront chat widget"]
)
public_router = APIRouter(prefix="/widget", tags=["Public storefront chat"])
VISITOR_SESSION_TTL = timedelta(hours=24)
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
MAX_HISTORY = 100


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
    if port and not ((parsed.scheme == "https" and port == 443) or (parsed.scheme == "http" and port == 80)):
        host = f"{host}:{port}"
    return f"{parsed.scheme}://{host}"


def normalized_origins(values: list[str]) -> list[str]:
    try:
        return sorted({normalize_origin(value) for value in values})
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def widget_out(widget: SupportWidget) -> WidgetConfigOut:
    return WidgetConfigOut(
        public_id=widget.public_id,
        allowed_origins=widget.allowed_origins,
        enabled=widget.enabled,
        collect_contact=widget.collect_contact,
        ai_enabled=widget.ai_enabled,
        ai_reply_mode=widget.ai_reply_mode,
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
            "visitor_email": str(payload.visitor_email).casefold() if payload.visitor_email else None,
            "contact_consent": payload.contact_consent,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hmac.new(settings.jwt_secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()


def key_hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def make_start_response(
    submission: WidgetSubmission, widget: SupportWidget
) -> WidgetStartOut:
    if submission.ticket_id is None or submission.conversation_id is None:
        raise HTTPException(status_code=503, detail="The conversation is still being created")
    if submission.visitor_token_expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="This visitor session expired. Start a new chat.")
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
        raise HTTPException(status_code=401, detail="Visitor session is invalid or expired") from None
    if token_conversation_id != conversation_id or not isinstance(public_id, str):
        raise HTTPException(status_code=403, detail="Visitor session cannot access this conversation")

    widget, _organization = await require_allowed_widget_origin(request, public_id, db)
    if widget.organization_id != organization_id:
        raise HTTPException(status_code=403, detail="Visitor session cannot access this conversation")
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


@management_router.get("", response_model=WidgetConfigOut | None)
async def get_widget_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WidgetConfigOut | None:
    widget = await db.scalar(
        select(SupportWidget)
        .where(SupportWidget.organization_id == user.organization_id)
        .order_by(SupportWidget.created_at.asc())
        .limit(1)
    )
    return widget_out(widget) if widget else None


@management_router.post("", response_model=WidgetConfigOut, status_code=status.HTTP_201_CREATED)
async def create_widget_config(
    data: WidgetConfigCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WidgetConfigOut:
    existing = await db.scalar(
        select(SupportWidget.id).where(SupportWidget.organization_id == user.organization_id).limit(1)
    )
    if existing:
        raise HTTPException(status_code=409, detail="A storefront widget already exists for this workspace")
    widget = SupportWidget(
        organization_id=user.organization_id,
        public_id=secrets.token_urlsafe(24),
        allowed_origins=normalized_origins(data.allowed_origins),
        collect_contact=data.collect_contact,
        ai_enabled=data.ai_enabled,
        ai_reply_mode=data.ai_reply_mode,
        enabled=True,
    )
    db.add(widget)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A storefront widget already exists for this workspace") from exc
    return widget_out(widget)


@management_router.put("", response_model=WidgetConfigOut)
async def update_widget_config(
    data: WidgetConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WidgetConfigOut:
    widget = await db.scalar(
        select(SupportWidget)
        .where(SupportWidget.organization_id == user.organization_id)
        .order_by(SupportWidget.created_at.asc())
        .limit(1)
        .with_for_update()
    )
    if widget is None:
        raise HTTPException(status_code=404, detail="Create a storefront widget first")
    widget.allowed_origins = normalized_origins(data.allowed_origins)
    widget.enabled = data.enabled
    widget.collect_contact = data.collect_contact
    widget.ai_enabled = data.ai_enabled
    widget.ai_reply_mode = data.ai_reply_mode
    await db.flush()
    return widget_out(widget)


@public_router.get("/{public_id}/config", response_model=PublicWidgetConfigOut)
async def public_widget_config(
    public_id: Annotated[str, Path(min_length=24, max_length=48, pattern=r"^[A-Za-z0-9_-]+$")],
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PublicWidgetConfigOut:
    await rate_limit_widget(request, public_id)
    widget, organization = await require_allowed_widget_origin(request, public_id, db)
    return PublicWidgetConfigOut(store_name=organization.name, collect_contact=widget.collect_contact)


@public_router.post(
    "/{public_id}/messages", response_model=WidgetStartOut, status_code=status.HTTP_201_CREATED
)
async def start_widget_conversation(
    public_id: Annotated[str, Path(min_length=24, max_length=48, pattern=r"^[A-Za-z0-9_-]+$")],
    payload: WidgetFirstMessage,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> WidgetStartOut:
    if not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="A valid idempotency key is required")
    if payload.website:
        raise HTTPException(status_code=422, detail="Message could not be accepted")
    await rate_limit_widget(request, public_id)
    widget, _organization = await require_allowed_widget_origin(request, public_id, db)
    if not widget.collect_contact and (payload.visitor_name or payload.visitor_email):
        raise HTTPException(status_code=422, detail="This widget does not collect contact details")
    fingerprint = request_hash(payload)
    hashed_key = key_hash(idempotency_key)
    now = datetime.now(UTC)
    expires_at = now + VISITOR_SESSION_TTL

    inserted = await db.scalar(
        pg_insert(WidgetSubmission)
        .values(
            organization_id=widget.organization_id,
            widget_id=widget.id,
            idempotency_key_hash=hashed_key,
            request_fingerprint=fingerprint,
            visitor_token_expires_at=expires_at,
            contact_consent=payload.contact_consent,
            contact_consent_at=now if payload.contact_consent else None,
            created_at=now,
        )
        .on_conflict_do_nothing(constraint="uq_widget_submissions_widget_key")
        .returning(WidgetSubmission.id)
    )
    if inserted is None:
        existing = await db.scalar(
            select(WidgetSubmission).where(
                WidgetSubmission.widget_id == widget.id,
                WidgetSubmission.idempotency_key_hash == hashed_key,
            )
        )
        if existing is None:
            raise HTTPException(status_code=409, detail="Retry this message with a new idempotency key")
        if not hmac.compare_digest(existing.request_fingerprint, fingerprint):
            raise HTTPException(status_code=409, detail="This idempotency key was used for a different message")
        return make_start_response(existing, widget)

    submission = await db.get(WidgetSubmission, inserted)
    if submission is None:
        raise HTTPException(status_code=503, detail="Message submission could not be initialized")

    customer_email = (
        str(payload.visitor_email).strip().casefold()
        if payload.visitor_email
        else f"visitor+{secrets.token_hex(12)}@widget.invalid"
    )
    customer_name = payload.visitor_name if payload.contact_consent and payload.visitor_name else "Store visitor"
    customer = Customer(organization_id=widget.organization_id, name=customer_name, email=customer_email)
    db.add(customer)
    await db.flush()

    first_line = " ".join(payload.content.split())
    subject = first_line[:237].rstrip() + ("…" if len(first_line) > 237 else "")
    ticket = Ticket(
        organization_id=widget.organization_id,
        customer_id=customer.id,
        subject=subject or "Storefront support request",
        description=payload.content,
        priority="normal",
        status="open",
        source="shopify_widget",
    )
    db.add(ticket)
    await db.flush()
    conversation = Conversation(
        organization_id=widget.organization_id,
        ticket_id=ticket.id,
        channel="shopify_widget",
        status="active",
    )
    db.add(conversation)
    await db.flush()
    message = Message(
        organization_id=widget.organization_id,
        conversation_id=conversation.id,
        sender_type="customer",
        sender_user_id=None,
        content=payload.content,
        content_type="text",
    )
    db.add(message)
    await db.flush()
    await enqueue_widget_reply(
        db=db, widget=widget, conversation=conversation, message=message
    )
    ticket.updated_at = now
    conversation.updated_at = now
    submission.ticket_id = ticket.id
    submission.conversation_id = conversation.id
    db.add(
        TicketActivity(
            organization_id=widget.organization_id,
            ticket_id=ticket.id,
            actor_user_id=None,
            activity_type="created",
            details={"source": "shopify_widget"},
        )
    )
    await db.flush()
    return make_start_response(submission, widget)


@public_router.get("/conversations/{conversation_id}", response_model=WidgetConversationOut)
async def get_widget_conversation(
    conversation_id: UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> WidgetConversationOut:
    _widget, conversation, _ticket = await require_visitor_conversation(
        request, conversation_id, authorization, db
    )
    messages = await db.scalars(
        select(Message)
        .where(
            Message.organization_id == conversation.organization_id,
            Message.conversation_id == conversation.id,
            Message.sender_type.in_(("customer", "agent", "assistant")),
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
        .limit(MAX_HISTORY)
    )
    return WidgetConversationOut(
        conversation_id=conversation.id,
        messages=[
            WidgetMessageOut(
                id=message.id,
                sender_type=message.sender_type,
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


@public_router.post("/conversations/{conversation_id}/messages", response_model=WidgetMessageOut)
async def continue_widget_conversation(
    conversation_id: UUID,
    payload: WidgetMessageCreate,
    request: Request,
    authorization: str | None = Header(default=None),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=128),
    db: AsyncSession = Depends(get_db),
) -> WidgetMessageOut:
    if not IDEMPOTENCY_PATTERN.fullmatch(idempotency_key):
        raise HTTPException(status_code=422, detail="A valid idempotency key is required")
    if payload.website:
        raise HTTPException(status_code=422, detail="Message could not be accepted")
    widget, conversation, ticket = await require_visitor_conversation(
        request, conversation_id, authorization, db
    )
    hashed_key = key_hash(idempotency_key)
    inserted_id = await db.scalar(
        pg_insert(Message)
        .values(
            organization_id=conversation.organization_id,
            conversation_id=conversation.id,
            sender_type="customer",
            sender_user_id=None,
            content=payload.content,
            content_type="text",
            widget_idempotency_hash=hashed_key,
        )
        .on_conflict_do_nothing(constraint="uq_messages_widget_idempotency")
        .returning(Message.id)
    )
    if inserted_id is None:
        existing = await db.scalar(
            select(Message).where(
                Message.organization_id == conversation.organization_id,
                Message.conversation_id == conversation.id,
                Message.widget_idempotency_hash == hashed_key,
            )
        )
        if existing is None:
            raise HTTPException(status_code=409, detail="Retry this message with a new idempotency key")
        if existing.content != payload.content:
            raise HTTPException(status_code=409, detail="This idempotency key was used for a different message")
        return WidgetMessageOut(id=existing.id, sender_type=existing.sender_type, content=existing.content, created_at=existing.created_at)
    message = await db.get(Message, inserted_id)
    if message is None:
        raise HTTPException(status_code=503, detail="Message could not be accepted")
    db.add(message)
    conversation.updated_at = datetime.now(UTC)
    ticket.updated_at = conversation.updated_at
    await enqueue_widget_reply(
        db=db, widget=widget, conversation=conversation, message=message
    )
    await db.flush()
    return WidgetMessageOut(
        id=message.id,
        sender_type=message.sender_type,
        content=message.content,
        created_at=message.created_at,
    )


def _verification_digest(verification_id: UUID, code: str) -> str:
    return hmac.new(
        settings.jwt_secret.encode(),
        f"{verification_id}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()


@public_router.post(
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
    widget, conversation, _ticket = await require_visitor_conversation(
        request, conversation_id, authorization, db
    )
    if not widget.ai_enabled:
        raise HTTPException(status_code=409, detail="AI support is not enabled for this store")
    if not smtp_is_configured():
        raise HTTPException(status_code=503, detail="Order verification email is not configured")

    from app.api.routes.integrations import ShopifyAPIError

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
        raise HTTPException(status_code=503, detail="Shopify order lookup is temporarily unavailable") from exc
    if order is None:
        # Do not reveal whether an email or order number exists in the store.
        return WidgetOrderVerificationOut(
            message="If the details match a recent order, a verification code has been sent to its checkout email."
        )

    now = datetime.now(UTC)
    await db.execute(
        select(WidgetOrderVerification)
        .where(
            WidgetOrderVerification.organization_id == widget.organization_id,
            WidgetOrderVerification.conversation_id == conversation.id,
            WidgetOrderVerification.status == "pending",
        )
        .with_for_update()
    )
    pending = list(await db.scalars(
        select(WidgetOrderVerification).where(
            WidgetOrderVerification.organization_id == widget.organization_id,
            WidgetOrderVerification.conversation_id == conversation.id,
            WidgetOrderVerification.status == "pending",
        )
    ))
    for previous in pending:
        previous.status = "expired"

    verification_id = uuid4()
    code = f"{secrets.randbelow(1_000_000):06d}"
    try:
        encrypted_email = encrypt_credential(str(payload.email).strip().casefold())
    except RuntimeError as exc:
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
        created_at=now,
    )
    db.add(verification)
    await db.commit()
    try:
        await send_order_verification_code(str(payload.email), code)
    except Exception as exc:  # SMTP errors must not leak addresses or provider details.
        verification.status = "expired"
        await db.commit()
        raise HTTPException(status_code=503, detail="Could not send the verification email") from exc
    return WidgetOrderVerificationOut(
        message="If the details match a recent order, a verification code has been sent to its checkout email."
    )


@public_router.post(
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
        raise HTTPException(status_code=400, detail="Code is invalid or expired. Request a new code.")
    supplied = _verification_digest(verification.id, payload.code)
    if not hmac.compare_digest(verification.code_digest, supplied):
        verification.attempt_count += 1
        if verification.attempt_count >= 5:
            verification.status = "locked"
        await db.commit()
        raise HTTPException(status_code=400, detail="Code is invalid or expired. Request a new code.")

    from app.api.routes.integrations import ShopifyAPIError, map_order

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
        raise HTTPException(status_code=503, detail="Shopify order lookup is temporarily unavailable") from exc
    if order is None or order.get("id") != verification.shopify_order_id:
        verification.status = "expired"
        await db.commit()
        raise HTTPException(status_code=409, detail="Order details changed. Please verify the order again.")

    mapped = map_order(order)
    parts = [f"I verified order {mapped.order_number}."]
    if mapped.fulfillment_status:
        parts.append(f"Fulfillment status: {mapped.fulfillment_status.replace('_', ' ').lower()}.")
    else:
        parts.append("This order has not been marked as fulfilled yet.")
    if mapped.tracking:
        tracking = mapped.tracking[0]
        if tracking.company:
            parts.append(f"Carrier: {tracking.company}.")
        if tracking.number:
            parts.append(f"Tracking number: {tracking.number}.")
        if tracking.url:
            parts.append(f"Tracking link: {tracking.url}")
    else:
        parts.append("The store has not provided tracking information for this order.")
    answer = " ".join(parts)
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
    await db.commit()
    return WidgetOrderVerificationOut(
        message=answer,
        verified=True,
        order_number=mapped.order_number,
        financial_status=mapped.financial_status,
        fulfillment_status=mapped.fulfillment_status,
        tracking=[item.model_dump() for item in mapped.tracking],
    )

