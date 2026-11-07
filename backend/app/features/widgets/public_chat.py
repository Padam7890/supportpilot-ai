"""Public widget configuration, conversation and recommendation event endpoints."""

"""Public, narrowly scoped Shopify storefront chat and tenant widget settings."""

import hmac
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Request, status
from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.features.automations.service import enqueue_customer_message_workflows
from app.models import (
    Conversation,
    Customer,
    Message,
    RecommendationEvent,
    SupportWidget,
    Ticket,
    TicketActivity,
    WidgetOrderVerification,
    WidgetSubmission,
)
from app.schemas.recommendation_settings import RecommendationEventIn, RecommendationEventOut
from app.schemas.widget import (
    PublicWidgetConfigOut,
    WidgetConversationOut,
    WidgetFirstMessage,
    WidgetMessageCreate,
    WidgetMessageOut,
    WidgetStartOut,
)
from app.services.widget_ai import enqueue_widget_reply

logger = logging.getLogger(__name__)
VISITOR_SESSION_TTL = timedelta(hours=24)
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
MAX_HISTORY = 100

router = APIRouter(prefix="/widget", tags=["Public storefront chat"])
from app.features.widgets.shared import (
    key_hash,
    make_start_response,
    rate_limit_widget,
    request_hash,
    require_allowed_widget_origin,
    require_visitor_conversation,
    widget_message_out,
)


@router.post(
    "/conversations/{conversation_id}/recommendation-events",
    response_model=RecommendationEventOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def record_recommendation_event(
    conversation_id: UUID,
    payload: RecommendationEventIn,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> RecommendationEventOut:
    """Record only widget events tied to a recommendation actually shown in this visitor's chat."""
    widget, conversation, _ticket = await require_visitor_conversation(
        request, conversation_id, authorization, db
    )
    message = await db.scalar(
        select(Message).where(
            Message.organization_id == widget.organization_id,
            Message.conversation_id == conversation.id,
            Message.id == payload.message_id,
            Message.sender_type == "assistant",
        )
    )
    raw = (
        message.provider_metadata.get("recommendation")
        if message and message.provider_metadata
        else None
    )
    if not isinstance(raw, dict):
        raise HTTPException(status_code=422, detail="This message has no recommendation data")
    if payload.event_type == "comparison" and raw.get("response_type") != "comparison":
        raise HTTPException(status_code=422, detail="This message is not a product comparison")
    if payload.event_type in {"impression", "product_click", "rejection"}:
        products = raw.get("products")
        product_ids = (
            {str(item.get("product_id")) for item in products if isinstance(item, dict)}
            if isinstance(products, list)
            else set()
        )
        if payload.event_type == "impression" and payload.product_id is None:
            raise HTTPException(
                status_code=422, detail="Product impression events require a product"
            )
        if payload.product_id is not None and str(payload.product_id) not in product_ids:
            raise HTTPException(status_code=422, detail="Product is not in this recommendation")
        if payload.variant_id is not None:
            product = (
                next(
                    (
                        item
                        for item in products
                        if isinstance(item, dict)
                        and str(item.get("product_id")) == str(payload.product_id)
                    ),
                    None,
                )
                if isinstance(products, list)
                else None
            )
            variants = product.get("variant_options", []) if product else []
            allowed_variants = (
                {str(item.get("variant_id")) for item in variants if isinstance(item, dict)}
                if isinstance(variants, list)
                else set()
            )
            if str(payload.variant_id) not in allowed_variants and str(payload.variant_id) != str(
                product.get("variant_id") if product else None
            ):
                raise HTTPException(
                    status_code=422, detail="Variant is not part of this product recommendation"
                )
    inserted = await db.execute(
        pg_insert(RecommendationEvent)
        .values(
            organization_id=widget.organization_id,
            event_id=payload.event_id,
            conversation_id=conversation.id,
            message_id=message.id,
            event_type=payload.event_type,
            product_id=payload.product_id,
            variant_id=payload.variant_id,
        )
        .on_conflict_do_nothing(constraint="uq_recommendation_events_org_event")
        .returning(RecommendationEvent.id)
    )
    if (
        inserted.scalar_one_or_none() is not None
        and payload.event_type == "rejection"
        and payload.product_id is not None
    ):
        state = dict(conversation.shopping_state or {})
        rejected = list(state.get("rejected_product_ids", []))
        if str(payload.product_id) not in {str(value) for value in rejected}:
            rejected.append(str(payload.product_id))
            state["rejected_product_ids"] = rejected[-50:]
            state["rejected_recommendation_count"] = min(
                100, int(state.get("rejected_recommendation_count", 0)) + 1
            )
            conversation.shopping_state = state
            conversation.shopping_state_updated_at = datetime.now(UTC)
            conversation.shopping_state_expires_at = datetime.now(UTC) + timedelta(days=30)
    return RecommendationEventOut()


@router.get("/{public_id}/config", response_model=PublicWidgetConfigOut)
async def public_widget_config(
    public_id: Annotated[str, Path(min_length=24, max_length=48, pattern=r"^[A-Za-z0-9_-]+$")],
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PublicWidgetConfigOut:
    await rate_limit_widget(request, public_id)
    widget, organization = await require_allowed_widget_origin(request, public_id, db)
    now = datetime.now(UTC)
    await db.execute(
        update(SupportWidget)
        .where(
            SupportWidget.id == widget.id,
            SupportWidget.organization_id == widget.organization_id,
            or_(
                SupportWidget.last_widget_load_at.is_(None),
                SupportWidget.last_widget_load_at < now - timedelta(minutes=5),
            ),
        )
        .values(last_widget_load_at=now)
        .execution_options(synchronize_session=False)
    )
    return PublicWidgetConfigOut(
        store_name=organization.name,
        collect_contact=widget.collect_contact,
        ai_enabled=widget.ai_enabled,
        assistant_name=widget.assistant_name,
        welcome_message=widget.welcome_message,
    )


@router.post(
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
            raise HTTPException(
                status_code=409, detail="Retry this message with a new idempotency key"
            )
        if not hmac.compare_digest(existing.request_fingerprint, fingerprint):
            raise HTTPException(
                status_code=409, detail="This idempotency key was used for a different message"
            )
        return make_start_response(existing, widget)

    submission = await db.get(WidgetSubmission, inserted)
    if submission is None:
        raise HTTPException(status_code=503, detail="Message submission could not be initialized")

    customer_email = (
        str(payload.visitor_email).strip().casefold()
        if payload.visitor_email
        else f"visitor+{secrets.token_hex(12)}@widget.invalid"
    )
    customer_name = (
        payload.visitor_name
        if payload.contact_consent and payload.visitor_name
        else "Store visitor"
    )
    customer = Customer(
        organization_id=widget.organization_id, name=customer_name, email=customer_email
    )
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
        ai_agent_id=widget.ai_agent_id,
        ai_mode="ai" if widget.ai_enabled else "human",
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
    await enqueue_widget_reply(db=db, widget=widget, conversation=conversation, message=message)
    await enqueue_customer_message_workflows(
        db,
        organization_id=widget.organization_id,
        ticket_id=ticket.id,
        conversation_id=conversation.id,
        message_id=message.id,
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


@router.get("/conversations/{conversation_id}", response_model=WidgetConversationOut)
async def get_widget_conversation(
    conversation_id: UUID,
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> WidgetConversationOut:
    widget, conversation, _ticket = await require_visitor_conversation(
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
    active_verification_id = await db.scalar(
        select(WidgetOrderVerification.id)
        .where(
            WidgetOrderVerification.organization_id == widget.organization_id,
            WidgetOrderVerification.widget_id == widget.id,
            WidgetOrderVerification.conversation_id == conversation.id,
            WidgetOrderVerification.status == "verified",
            WidgetOrderVerification.expires_at > datetime.now(UTC),
        )
        .order_by(WidgetOrderVerification.verified_at.desc())
        .limit(1)
    )
    return WidgetConversationOut(
        conversation_id=conversation.id,
        order_verified=active_verification_id is not None,
        ai_mode=conversation.ai_mode,
        messages=[widget_message_out(message) for message in messages],
    )


@router.post("/conversations/{conversation_id}/messages", response_model=WidgetMessageOut)
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
    recommendation_selections: list[dict[str, str]] = []
    if payload.recommendation_selections:
        selections = payload.recommendation_selections
        if not 2 <= len(selections) <= 4 or len(
            {selection.product_id for selection in selections}
        ) != len(selections):
            raise HTTPException(
                status_code=422, detail="Select 2–4 different displayed products to compare"
            )
        selection_expires_at = conversation.shopping_state_expires_at
        if selection_expires_at is None:
            raise HTTPException(
                status_code=422,
                detail="Those recommendations have expired; please ask for options again",
            )
        normalized_expiry = (
            selection_expires_at
            if selection_expires_at.tzinfo is not None
            else selection_expires_at.replace(tzinfo=UTC)
        )
        if normalized_expiry <= datetime.now(UTC):
            raise HTTPException(
                status_code=422,
                detail="Those recommendations have expired; please ask for options again",
            )
        raw_state = conversation.shopping_state or {}
        displayed = (
            raw_state.get("last_displayed_recommendations", [])
            if isinstance(raw_state, dict)
            else []
        )
        available_by_product: dict[str, set[str]] = {}
        if isinstance(displayed, list):
            for item in displayed:
                if not isinstance(item, dict):
                    continue
                product_id = item.get("product_id")
                variant_id = item.get("variant_id")
                if not isinstance(product_id, str) or not isinstance(variant_id, str):
                    continue
                options = item.get("available_variant_ids")
                allowed = (
                    {value for value in options if isinstance(value, str)}
                    if isinstance(options, list)
                    else set()
                )
                allowed.add(variant_id)
                available_by_product[product_id] = allowed
        if any(
            str(selection.product_id) not in available_by_product
            or str(selection.variant_id) not in available_by_product[str(selection.product_id)]
            for selection in selections
        ):
            raise HTTPException(
                status_code=422,
                detail="A selected option is no longer in this chat’s recommendations",
            )
        recommendation_selections = [selection.model_dump(mode="json") for selection in selections]
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
            provider_metadata=(
                {"recommendation_selections": recommendation_selections}
                if recommendation_selections
                else {}
            ),
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
            raise HTTPException(
                status_code=409, detail="Retry this message with a new idempotency key"
            )
        if existing.content != payload.content:
            raise HTTPException(
                status_code=409, detail="This idempotency key was used for a different message"
            )
        existing_selections = existing.provider_metadata.get("recommendation_selections", [])
        if existing_selections != recommendation_selections:
            raise HTTPException(
                status_code=409, detail="This idempotency key was used for a different comparison"
            )
        return WidgetMessageOut(
            id=existing.id,
            sender_type=existing.sender_type,
            content=existing.content,
            created_at=existing.created_at,
        )
    message = await db.get(Message, inserted_id)
    if message is None:
        raise HTTPException(status_code=503, detail="Message could not be accepted")
    db.add(message)
    conversation.updated_at = datetime.now(UTC)
    ticket.updated_at = conversation.updated_at
    await enqueue_widget_reply(db=db, widget=widget, conversation=conversation, message=message)
    await enqueue_customer_message_workflows(
        db,
        organization_id=conversation.organization_id,
        ticket_id=ticket.id,
        conversation_id=conversation.id,
        message_id=message.id,
    )
    await db.flush()
    return WidgetMessageOut(
        id=message.id,
        sender_type=message.sender_type,
        content=message.content,
        created_at=message.created_at,
    )

