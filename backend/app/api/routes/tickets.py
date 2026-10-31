from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import Ticket, TicketActivity, User
from app.repositories.customer import CustomerRepository
from app.repositories.ticket import TicketRepository
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.ticket import (
    TicketActivityOut,
    TicketCreate,
    TicketOut,
    TicketPage,
    TicketStatsOut,
    TicketUpdate,
    TicketVolumeOut,
)
from app.services.ticket import TicketService

router = APIRouter(prefix="/tickets", tags=["tickets"], responses=COMMON_ERROR_RESPONSES)


def service(db: AsyncSession) -> TicketService:
    return TicketService(TicketRepository(db), CustomerRepository(db))


@router.get("/stats", response_model=TicketStatsOut)
async def ticket_stats(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketStatsOut:
    today = date.today()
    end = end_date or today
    start = start_date or (end - timedelta(days=29))
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if (end - start).days > 365:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 366 days")
    counts = await db.execute(
        select(Ticket.status, func.count(Ticket.id))
        .where(Ticket.organization_id == user.organization_id)
        .group_by(Ticket.status)
    )
    by_status = {str(ticket_status): int(count) for ticket_status, count in counts.all()}
    priorities = await db.execute(
        select(Ticket.priority, func.count(Ticket.id))
        .where(Ticket.organization_id == user.organization_id)
        .group_by(Ticket.priority)
    )
    by_priority = {str(priority): int(count) for priority, count in priorities.all()}
    daily = await db.execute(
        select(func.date(Ticket.created_at), func.count(Ticket.id))
        .where(
            Ticket.organization_id == user.organization_id,
            func.date(Ticket.created_at) >= start,
            func.date(Ticket.created_at) <= end,
        )
        .group_by(func.date(Ticket.created_at))
        .order_by(func.date(Ticket.created_at))
    )
    daily_map = {day: int(count) for day, count in daily.all()}
    volume = [
        TicketVolumeOut(date=day, count=daily_map.get(day, 0))
        for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
    ]
    return TicketStatsOut(
        total_tickets=sum(by_status.values()),
        open_tickets=by_status.get("open", 0),
        pending_tickets=by_status.get("pending", 0),
        resolved_tickets=by_status.get("resolved", 0),
        closed_tickets=by_status.get("closed", 0),
        by_status=by_status,
        by_priority=by_priority,
        volume=volume,
    )


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    data: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> TicketOut:
    return await service(db).create(user.organization_id, data, actor_user_id=user.id)


@router.get("", response_model=TicketPage)
async def list_tickets(
    search: str | None = Query(default=None, max_length=200),
    ticket_status: str | None = Query(
        default=None, alias="status", pattern="^(open|pending|resolved|closed)$"
    ),
    priority: str | None = Query(default=None, pattern="^(low|normal|high|urgent)$"),
    assignee_id: UUID | None = None,
    customer_id: UUID | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketPage:
    items, total = await TicketRepository(db).search_page(
        user.organization_id,
        search=search,
        status=ticket_status,
        priority=priority,
        assignee_id=assignee_id,
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )
    return TicketPage(
        items=[
            TicketOut.model_validate(ticket).model_copy(
                update={
                    "customer_name": ticket.customer.name if ticket.customer else None,
                    "assignee_name": ticket.assignee.full_name if ticket.assignee else None,
                }
            )
            for ticket in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    ticket = await service(db).get(user.organization_id, ticket_id)
    return TicketOut.model_validate(ticket).model_copy(
        update={
            "customer_name": ticket.customer.name if ticket.customer else None,
            "assignee_name": ticket.assignee.full_name if ticket.assignee else None,
        }
    )


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: UUID,
    data: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> TicketOut:
    changes = data.model_dump(exclude_unset=True)
    if "assignee_id" in changes and user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only owners and admins can assign tickets")
    ticket = await service(db).update(user.organization_id, ticket_id, data, actor_user_id=user.id)
    return TicketOut.model_validate(ticket).model_copy(
        update={
            "customer_name": ticket.customer.name if ticket.customer else None,
            "assignee_name": ticket.assignee.full_name if ticket.assignee else None,
        }
    )


@router.get("/{ticket_id}/activity", response_model=list[TicketActivityOut])
async def ticket_activity(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TicketActivityOut]:
    ticket = await TicketRepository(db).get(user.organization_id, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    rows = await db.execute(
        select(TicketActivity, User.full_name)
        .outerjoin(
            User,
            (User.id == TicketActivity.actor_user_id)
            & (User.organization_id == user.organization_id),
        )
        .where(
            TicketActivity.organization_id == user.organization_id,
            TicketActivity.ticket_id == ticket_id,
        )
        .order_by(TicketActivity.created_at.asc())
    )
    return [
        TicketActivityOut(
            id=activity.id,
            ticket_id=activity.ticket_id,
            actor_user_id=activity.actor_user_id,
            actor_name=actor_name,
            activity_type=activity.activity_type,
            details=activity.details,
            created_at=activity.created_at,
        )
        for activity, actor_name in rows.all()
    ]
