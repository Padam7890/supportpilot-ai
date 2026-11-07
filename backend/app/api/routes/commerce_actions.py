from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.api.deps import get_current_user, require_roles
from app.core.observability import current_correlation_id
from app.db.session import get_db, set_tenant_context
from app.integrations.providers.shopify.actions import (
    ShopifyOrderActionError,
    check_cancellation_eligibility,
    check_cancellation_scope,
)
from app.models import CommerceAction, CommerceActionAudit, Customer, Ticket, User
from app.schemas.commerce_action import (
    CommerceActionAuditOut,
    CommerceActionAuditPage,
    CommerceActionCreate,
    CommerceActionOut,
    CommerceActionPage,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.services.shopify_access import installation_for
from app.services.shopify_order_lookup import verified_lookup
from app.services.commerce_action_identity import (
    commerce_action_fingerprint,
    commerce_idempotency_hash,
)

router = APIRouter(
    prefix="/commerce/actions", tags=["Commerce actions"], responses=COMMON_ERROR_RESPONSES
)
IDEMPOTENCY_KEY_MAX_LENGTH = 128
ACTION_TTL = timedelta(days=7)


def action_out(
    action: CommerceAction, requested_by_name: str, reviewed_by_name: str | None
) -> CommerceActionOut:
    fields = CommerceActionOut.model_fields
    values = {name: getattr(action, name) for name in fields if hasattr(action, name)}
    values.update(requested_by_name=requested_by_name, reviewed_by_name=reviewed_by_name)
    return CommerceActionOut.model_validate(values)


async def get_action(
    db: AsyncSession, organization_id: UUID, action_id: UUID, *, lock: bool = False
) -> CommerceAction:
    statement = select(CommerceAction).where(
        CommerceAction.organization_id == organization_id,
        CommerceAction.id == action_id,
    )
    if lock:
        statement = statement.with_for_update()
    action = await db.scalar(statement)
    if action is None:
        raise HTTPException(status_code=404, detail="Commerce action not found")
    return action


async def serialize_action(db: AsyncSession, action: CommerceAction) -> CommerceActionOut:
    requester = aliased(User)
    reviewer = aliased(User)
    row = await db.execute(
        select(requester.full_name, reviewer.full_name)
        .select_from(CommerceAction)
        .outerjoin(
            requester,
            (requester.organization_id == CommerceAction.organization_id)
            & (requester.id == CommerceAction.requested_by_user_id),
        )
        .outerjoin(
            reviewer,
            (reviewer.organization_id == CommerceAction.organization_id)
            & (reviewer.id == CommerceAction.reviewed_by_user_id),
        )
        .where(
            CommerceAction.organization_id == action.organization_id,
            CommerceAction.id == action.id,
        )
    )
    names = row.one()
    return action_out(action, names[0] or "Customer via storefront chat", names[1])


def add_audit(
    db: AsyncSession,
    action: CommerceAction,
    *,
    actor_user_id: UUID | None,
    event_type: str,
    details: dict,
) -> None:
    db.add(
        CommerceActionAudit(
            organization_id=action.organization_id,
            commerce_action_id=action.id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            details=details,
        )
    )


@router.post("", response_model=CommerceActionOut, status_code=status.HTTP_201_CREATED)
async def create_commerce_action(
    data: CommerceActionCreate,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=16, max_length=IDEMPOTENCY_KEY_MAX_LENGTH
    ),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> CommerceActionOut:
    normalized_key = idempotency_key.strip()
    key_digest = commerce_idempotency_hash(normalized_key)
    request_digest = commerce_action_fingerprint(data)
    existing = await db.scalar(
        select(CommerceAction).where(
            CommerceAction.organization_id == user.organization_id,
            CommerceAction.idempotency_key_hash == key_digest,
        )
    )
    if existing is not None:
        if existing.request_fingerprint != request_digest:
            raise HTTPException(
                status_code=409, detail="Idempotency-Key was already used for a different request"
            )
        return await serialize_action(db, existing)

    ticket_customer = await db.execute(
        select(Ticket, Customer)
        .join(
            Customer,
            (Customer.organization_id == Ticket.organization_id)
            & (Customer.id == Ticket.customer_id),
        )
        .where(
            Ticket.organization_id == user.organization_id,
            Ticket.id == data.ticket_id,
        )
    )
    row = ticket_customer.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    _ticket, customer = row
    if not customer.email:
        raise HTTPException(
            status_code=409, detail="This ticket has no customer email to verify the order"
        )

    if data.provider == "shopify":
        if data.action_type != "cancel":
            raise HTTPException(
                status_code=422, detail="Only cancellation actions can execute against Shopify"
            )
        installation = await installation_for(db, user.organization_id)
        try:
            check_cancellation_scope(installation.granted_scopes)
        except ShopifyOrderActionError:
            raise HTTPException(
                status_code=403,
                detail="Shopify has not granted write_orders for order cancellation",
            )

    # A ticket's CRM customer email plus Shopify order number must verify before
    # an action can be requested. The client cannot supply another customer's email.
    verified = await verified_lookup(
        db=db,
        user=user,
        customer_email=customer.email,
        order_number=data.order_number,
        limit=1,
        cursor=None,
    )
    order = verified.matched_order
    if data.provider == "shopify":
        try:
            check_cancellation_eligibility(
                {
                    "cancelledAt": order.cancelled_at,
                    "closed": order.closed,
                    "returnStatus": order.return_status,
                }
            )
        except ShopifyOrderActionError as exc:
            detail = {
                "shopify_order_already_cancelled": "This Shopify order is already cancelled.",
                "shopify_order_not_cancelable": "This Shopify order is closed and cannot be cancelled.",
                "shopify_order_has_active_return": "This Shopify order has an active return and cannot be cancelled.",
            }.get(exc.code, "This Shopify order is not eligible for cancellation.")
            raise HTTPException(status_code=409, detail=detail) from exc
    try:
        order_total = Decimal(order.total_amount)
    except InvalidOperation as exc:
        raise HTTPException(
            status_code=502, detail="Shopify returned an invalid order total"
        ) from exc
    if data.action_type == "refund":
        if data.refund_amount is None or data.refund_amount > order_total:
            raise HTTPException(
                status_code=422, detail="Refund amount cannot exceed the verified order total"
            )
        if (order.financial_status or "").casefold() not in {"paid", "partially_refunded"}:
            raise HTTPException(
                status_code=409, detail="Only paid orders can be submitted for refund review"
            )
    now = datetime.now(UTC)
    action = CommerceAction(
        organization_id=user.organization_id,
        ticket_id=data.ticket_id,
        requested_by_user_id=user.id,
        action_type=data.action_type,
        provider=data.provider,
        shopify_order_id=order.id,
        order_number=order.order_number,
        order_total=order_total,
        currency=order.currency,
        refund_amount=data.refund_amount,
        cancel_refund=data.cancel_refund,
        cancel_restock=data.cancel_restock,
        cancel_notify_customer=data.cancel_notify_customer,
        cancellation_reason=data.cancellation_reason,
        reason=data.reason,
        idempotency_key_hash=key_digest,
        request_fingerprint=request_digest,
        approval_status="pending",
        expires_at=now + ACTION_TTL,
        execution_status="not_started",
        correlation_id=current_correlation_id(),
    )
    db.add(action)
    try:
        await db.flush()
    except IntegrityError:
        # Two identical requests can race after the initial lookup. The
        # organization-scoped unique key chooses one winner; the loser reads
        # and returns that canonical action without creating a second record.
        await db.rollback()
        await set_tenant_context(db, user.organization_id)
        existing = await db.scalar(
            select(CommerceAction).where(
                CommerceAction.organization_id == user.organization_id,
                CommerceAction.idempotency_key_hash == key_digest,
            )
        )
        if existing is None:
            raise HTTPException(
                status_code=409, detail="A conflicting commerce action was submitted"
            )
        if existing.request_fingerprint != request_digest:
            raise HTTPException(
                status_code=409, detail="Idempotency-Key was already used for a different request"
            )
        return await serialize_action(db, existing)
    add_audit(
        db,
        action,
        actor_user_id=user.id,
        event_type="requested",
        details={
            "action_type": action.action_type,
            "provider": action.provider,
            "order_number": action.order_number,
            "shopify_order_id": action.shopify_order_id,
            "cancel_refund": action.cancel_refund,
            "cancel_restock": action.cancel_restock,
            "cancel_notify_customer": action.cancel_notify_customer,
            "cancellation_reason": action.cancellation_reason,
            "approval_status": action.approval_status,
            "execution_status": action.execution_status,
        },
    )
    await db.flush()
    return await serialize_action(db, action)


@router.get("", response_model=CommerceActionPage)
async def list_commerce_actions(
    ticket_id: UUID | None = None,
    approval_status: str | None = Query(
        default=None, pattern="^(pending|approved|rejected|expired|cancelled)$"
    ),
    execution_status: str | None = Query(
        default=None, pattern="^(not_started|queued|running|succeeded|failed)$"
    ),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CommerceActionPage:
    filters = [CommerceAction.organization_id == user.organization_id]
    if ticket_id:
        filters.append(CommerceAction.ticket_id == ticket_id)
    if approval_status:
        filters.append(CommerceAction.approval_status == approval_status)
    if execution_status:
        filters.append(CommerceAction.execution_status == execution_status)
    total = await db.scalar(select(func.count()).select_from(CommerceAction).where(*filters)) or 0
    requester = aliased(User)
    reviewer = aliased(User)
    results = await db.execute(
        select(CommerceAction, requester.full_name, reviewer.full_name)
        # Widget-submitted requests have no workspace user requester. Keep
        # those rows in the queue and label them as storefront customers.
        .outerjoin(
            requester,
            (requester.organization_id == CommerceAction.organization_id)
            & (requester.id == CommerceAction.requested_by_user_id),
        )
        .outerjoin(
            reviewer,
            (reviewer.organization_id == CommerceAction.organization_id)
            & (reviewer.id == CommerceAction.reviewed_by_user_id),
        )
        .where(*filters)
        .order_by(CommerceAction.created_at.desc(), CommerceAction.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return CommerceActionPage(
        items=[
            action_out(action, requester_name or "Customer via storefront chat", reviewer_name)
            for action, requester_name, reviewer_name in results.all()
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{action_id}", response_model=CommerceActionOut)
async def get_commerce_action(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CommerceActionOut:
    action = await get_action(db, user.organization_id, action_id)
    return await serialize_action(db, action)


@router.get("/{action_id}/audit", response_model=CommerceActionAuditPage)
async def list_commerce_action_audit(
    action_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CommerceActionAuditPage:
    await get_action(db, user.organization_id, action_id)
    filters = [
        CommerceActionAudit.organization_id == user.organization_id,
        CommerceActionAudit.commerce_action_id == action_id,
    ]
    total = (
        await db.scalar(select(func.count()).select_from(CommerceActionAudit).where(*filters)) or 0
    )
    rows = await db.execute(
        select(CommerceActionAudit, User.full_name)
        .outerjoin(
            User,
            (User.organization_id == CommerceActionAudit.organization_id)
            & (User.id == CommerceActionAudit.actor_user_id),
        )
        .where(*filters)
        .order_by(CommerceActionAudit.created_at.asc(), CommerceActionAudit.id.asc())
        .limit(limit)
        .offset(offset)
    )
    return CommerceActionAuditPage(
        items=[
            CommerceActionAuditOut(
                id=audit.id,
                actor_user_id=audit.actor_user_id,
                actor_name=actor_name,
                event_type=audit.event_type,
                details=audit.details,
                created_at=audit.created_at,
            )
            for audit, actor_name in rows.all()
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{action_id}/approve", response_model=CommerceActionOut)
async def approve_commerce_action(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> CommerceActionOut:
    action = await get_action(db, user.organization_id, action_id, lock=True)
    now = datetime.now(UTC)
    if action.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Only pending actions can be approved")
    if action.expires_at <= now:
        action.approval_status = "expired"
        add_audit(
            db,
            action,
            actor_user_id=None,
            event_type="expired",
            details={"reason": "approval_window_elapsed"},
        )
        await db.commit()
        await set_tenant_context(db, user.organization_id)
        raise HTTPException(status_code=409, detail="This action expired before approval")
    action.approval_status = "approved"
    action.execution_status = "queued"
    action.reviewed_by_user_id = user.id
    action.reviewed_at = now
    add_audit(
        db,
        action,
        actor_user_id=user.id,
        event_type="approved",
        details={"approval_status": "approved", "execution_status": "queued"},
    )
    await db.flush()
    return await serialize_action(db, action)


@router.post("/{action_id}/reject", response_model=CommerceActionOut)
async def reject_commerce_action(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> CommerceActionOut:
    action = await get_action(db, user.organization_id, action_id, lock=True)
    if action.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Only pending actions can be rejected")
    now = datetime.now(UTC)
    action.approval_status = "rejected"
    action.reviewed_by_user_id = user.id
    action.reviewed_at = now
    add_audit(
        db,
        action,
        actor_user_id=user.id,
        event_type="rejected",
        details={"approval_status": "rejected", "execution_status": "not_started"},
    )
    await db.flush()
    return await serialize_action(db, action)


@router.post("/{action_id}/cancel", response_model=CommerceActionOut)
async def cancel_commerce_action(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> CommerceActionOut:
    action = await get_action(db, user.organization_id, action_id, lock=True)
    if action.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Only pending actions can be cancelled")
    if action.requested_by_user_id != user.id and user.role not in {"owner", "admin"}:
        raise HTTPException(
            status_code=403, detail="Agents can cancel only their own pending requests"
        )
    now = datetime.now(UTC)
    action.approval_status = "cancelled"
    action.cancelled_by_user_id = user.id
    action.cancelled_at = now
    add_audit(
        db,
        action,
        actor_user_id=user.id,
        event_type="cancelled",
        details={"approval_status": "cancelled", "execution_status": "not_started"},
    )
    await db.flush()
    return await serialize_action(db, action)
