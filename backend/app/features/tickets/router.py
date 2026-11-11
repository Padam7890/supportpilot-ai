from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.features.customers.repository import CustomerRepository
from app.features.tickets.link_service import TicketLinkService
from app.features.tickets.repository import TicketRepository
from app.features.tickets.service import TicketService
from app.models import Team, TeamMember, Ticket, TicketActivity, User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.ticket import (
    TicketActivityOut,
    TicketBulkUpdate,
    TicketBulkUpdateOut,
    TicketCreate,
    TicketLinkCreate,
    TicketLinkOut,
    TicketLinkPage,
    TicketOut,
    TicketPage,
    TicketStatsOut,
    TicketUpdate,
    TicketVolumeOut,
)

router = APIRouter(prefix="/tickets", tags=["tickets"], responses=COMMON_ERROR_RESPONSES)


def service(db: AsyncSession) -> TicketService:
    return TicketService(TicketRepository(db), CustomerRepository(db))


def ticket_output(ticket: Ticket) -> TicketOut:
    return TicketOut.model_validate(ticket).model_copy(
        update={
            "customer_name": ticket.customer.name if ticket.customer else None,
            "assignee_name": ticket.assignee.full_name if ticket.assignee else None,
            "team_name": ticket.team.name if ticket.team else None,
        }
    )


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
    if data.team_id is not None and user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only Owners and Admins can route tickets to a team")
    ticket = await service(db).create(user.organization_id, data, actor_user_id=user.id)
    return ticket_output(ticket)


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
            ticket_output(ticket)
            for ticket in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.patch("/bulk", response_model=TicketBulkUpdateOut)
async def bulk_update_tickets(
    data: TicketBulkUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> TicketBulkUpdateOut:
    if data.model_fields_set.intersection({"assignee_id", "team_id"}) and user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only Owners and Admins can assign tickets and teams")
    changed_count, ticket_ids = await service(db).bulk_update(
        user.organization_id,
        data,
        actor_user_id=user.id,
    )
    return TicketBulkUpdateOut(
        updated_count=len(ticket_ids),
        changed_count=changed_count,
        ticket_ids=ticket_ids,
    )


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    ticket = await service(db).get(user.organization_id, ticket_id)
    return ticket_output(ticket)


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: UUID,
    data: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> TicketOut:
    changes = data.model_dump(exclude_unset=True)
    if changes.keys() & {"assignee_id", "team_id"} and user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only Owners and Admins can assign tickets and teams")
    ticket = await service(db).update(user.organization_id, ticket_id, data, actor_user_id=user.id)
    return ticket_output(ticket)


@router.post("/{ticket_id}/assign-to-me", response_model=TicketOut)
async def assign_ticket_to_me(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> TicketOut:
    ticket = await db.scalar(
        select(Ticket)
        .where(Ticket.organization_id == user.organization_id, Ticket.id == ticket_id)
        .with_for_update()
    )
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.team_id is not None:
        await db.scalar(
            select(Team)
            .where(Team.organization_id == user.organization_id, Team.id == ticket.team_id)
            .with_for_update()
        )
        member_id = await db.scalar(
            select(TeamMember.user_id)
            .where(
                TeamMember.organization_id == user.organization_id,
                TeamMember.team_id == ticket.team_id,
                TeamMember.user_id == user.id,
            )
            .with_for_update()
        )
        if member_id is None:
            raise HTTPException(status_code=403, detail="Join this ticket's team before claiming it")
    if ticket.assignee_id not in (None, user.id):
        raise HTTPException(status_code=409, detail="Ticket is already assigned to another teammate")
    if ticket.assignee_id is None:
        ticket.assignee_id = user.id
        db.add(
            TicketActivity(
                organization_id=user.organization_id,
                ticket_id=ticket.id,
                actor_user_id=user.id,
                activity_type="updated",
                details={"assignee_id": {"from": None, "to": str(user.id)}},
            )
        )
        await db.flush()
    refreshed = await service(db).get(user.organization_id, ticket_id)
    return ticket_output(refreshed)


@router.get("/{ticket_id}/links", response_model=TicketLinkPage)
async def list_ticket_links(
    ticket_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketLinkPage:
    items, total = await TicketLinkService(db).list_for_ticket(
        user.organization_id,
        ticket_id,
        limit=limit,
        offset=offset,
    )
    return TicketLinkPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{ticket_id}/link-candidates", response_model=TicketPage)
async def search_ticket_link_candidates(
    ticket_id: UUID,
    search: str = Query(min_length=2, max_length=200),
    limit: int = Query(10, ge=1, le=20),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketPage:
    search = search.strip()
    if len(search) < 2:
        raise HTTPException(status_code=422, detail="Search must contain at least two non-space characters")
    repository = TicketRepository(db)
    if not await repository.exists(user.organization_id, ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    items, total = await repository.search_link_candidates(
        user.organization_id,
        ticket_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return TicketPage(
        items=[
            ticket_output(ticket)
            for ticket in items
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/{ticket_id}/links", response_model=TicketLinkOut, status_code=status.HTTP_201_CREATED)
async def create_ticket_link(
    ticket_id: UUID,
    data: TicketLinkCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> TicketLinkOut:
    return await TicketLinkService(db).create(
        user.organization_id,
        ticket_id,
        data.related_ticket_id,
        user.id,
    )


@router.delete("/{ticket_id}/links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_ticket_link(
    ticket_id: UUID,
    link_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> None:
    await TicketLinkService(db).remove(
        user.organization_id,
        ticket_id,
        link_id,
        user.id,
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
