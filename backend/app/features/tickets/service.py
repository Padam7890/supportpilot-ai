from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select

from app.features.customers.repository import CustomerRepository
from app.features.notifications.application.events import (
    TicketNotificationPayload,
    enqueue_notification_event,
)
from app.features.tickets.repository import TicketRepository
from app.models import Team, TeamMember, Ticket, TicketActivity, User
from app.schemas.ticket import TicketBulkUpdate, TicketCreate, TicketUpdate


class TicketService:
    def __init__(self, repo: TicketRepository, customers: CustomerRepository):
        self.repo = repo
        self.customers = customers

    async def create(
        self, organization_id: UUID, data: TicketCreate, actor_user_id: UUID | None = None
    ):
        customer = await self.customers.get(organization_id, data.customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        if data.team_id is not None:
            await self._validate_team_assignment(organization_id, data.team_id, None)
        ticket = Ticket(organization_id=organization_id, **data.model_dump())
        await self.repo.add(ticket)
        self.repo.session.add(
            TicketActivity(
                organization_id=organization_id,
                ticket_id=ticket.id,
                actor_user_id=actor_user_id,
                activity_type="created",
                details={"subject": ticket.subject},
            )
        )
        await self.repo.session.flush()
        return await self.repo.get(organization_id, ticket.id)

    async def get(self, organization_id: UUID, ticket_id: UUID):
        ticket = await self.repo.get(organization_id, ticket_id)
        if not ticket:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return ticket

    async def list_tickets(self, organization_id: UUID, limit: int, offset: int):
        """List tickets for pagination. Named `list_tickets` so the class body does not shadow `list`."""
        return await self.repo.list(organization_id, limit=limit, offset=offset)

    async def update(
        self,
        organization_id: UUID,
        ticket_id: UUID,
        data: TicketUpdate,
        actor_user_id: UUID | None = None,
    ):
        ticket = await self.repo.get_locked(organization_id, ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found")
        changes = data.model_dump(exclude_unset=True)
        if "assignee_id" in changes and changes["assignee_id"] is not None:
            result = await self.repo.session.execute(
                select(User).where(
                    User.id == changes["assignee_id"],
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                    User.role.in_(("owner", "admin", "agent")),
                )
            )
            if result.scalar_one_or_none() is None:
                raise HTTPException(status_code=404, detail="Assignee not found")
        resulting_team_id = changes.get("team_id", ticket.team_id)
        resulting_assignee_id = changes.get("assignee_id", ticket.assignee_id)
        if "team_id" in changes and resulting_team_id is not None or "assignee_id" in changes and resulting_assignee_id is not None and resulting_team_id is not None:
            await self._validate_team_assignment(
                organization_id,
                resulting_team_id,
                resulting_assignee_id,
            )
        changed = {}
        for key, value in changes.items():
            previous = getattr(ticket, key)
            if previous != value:
                changed[key] = {
                    "from": str(previous) if previous is not None else None,
                    "to": str(value) if value is not None else None,
                }
            setattr(ticket, key, value)
        await self.repo.session.flush()
        if changed:
            self.repo.session.add(
                TicketActivity(
                    organization_id=organization_id,
                    ticket_id=ticket_id,
                    actor_user_id=actor_user_id,
                    activity_type="updated",
                    details=changed,
                )
            )
            await self.repo.session.flush()
            if "assignee_id" in changed and resulting_assignee_id is not None and resulting_assignee_id != actor_user_id:
                await enqueue_notification_event(
                    self.repo.session,
                    organization_id=organization_id,
                    event_type="ticket.assigned",
                    aggregate_type="ticket",
                    aggregate_id=ticket_id,
                    payload=TicketNotificationPayload(
                        ticket_id=ticket_id,
                        actor_user_id=actor_user_id,
                        recipient_user_id=resulting_assignee_id,
                        team_id=resulting_team_id,
                    ),
                )
        return await self.repo.get(organization_id, ticket_id)

    async def bulk_update(
        self,
        organization_id: UUID,
        data: TicketBulkUpdate,
        actor_user_id: UUID,
    ) -> tuple[int, list[UUID]]:
        changes = data.model_dump(exclude={"ticket_ids"}, exclude_unset=True)
        tickets = await self.repo.lock_many(organization_id, data.ticket_ids)
        if len(tickets) != len(data.ticket_ids):
            raise HTTPException(status_code=404, detail="One or more tickets were not found")

        assignee_id = changes.get("assignee_id")
        if assignee_id is not None:
            assignee = await self.repo.session.scalar(
                select(User).where(
                    User.id == assignee_id,
                    User.organization_id == organization_id,
                    User.is_active.is_(True),
                    User.role.in_(("owner", "admin", "agent")),
                )
            )
            if assignee is None:
                raise HTTPException(status_code=404, detail="Assignee not found")

        team_id = changes.get("team_id")
        if "team_id" in changes and team_id is not None:
            await self._validate_team_assignment(organization_id, team_id, assignee_id)
            if assignee_id is None and "assignee_id" not in changes:
                existing_assignees = {ticket.assignee_id for ticket in tickets if ticket.assignee_id is not None}
                if existing_assignees:
                    valid_member_ids = set(
                        await self.repo.session.scalars(
                            select(TeamMember.user_id).where(
                                TeamMember.organization_id == organization_id,
                                TeamMember.team_id == team_id,
                                TeamMember.user_id.in_(existing_assignees),
                            )
                        )
                    )
                    if valid_member_ids != existing_assignees:
                        raise HTTPException(
                            status_code=409,
                            detail="Every currently assigned teammate must belong to the selected team",
                        )
        elif assignee_id is not None:
            tickets_with_teams = [ticket for ticket in tickets if ticket.team_id is not None]
            if tickets_with_teams:
                membership_pairs = set(
                    await self.repo.session.execute(
                        select(TeamMember.team_id, TeamMember.user_id).where(
                            TeamMember.organization_id == organization_id,
                            TeamMember.team_id.in_({ticket.team_id for ticket in tickets_with_teams}),
                            TeamMember.user_id == assignee_id,
                        )
                    )
                )
                if any((ticket.team_id, assignee_id) not in membership_pairs for ticket in tickets_with_teams):
                    raise HTTPException(
                        status_code=409,
                        detail="The selected teammate must belong to every affected ticket team",
                    )

        changed_count = 0
        for ticket in tickets:
            details = {}
            for field, value in changes.items():
                previous = getattr(ticket, field)
                if previous == value:
                    continue
                details[field] = {
                    "from": str(previous) if previous is not None else None,
                    "to": str(value) if value is not None else None,
                }
                setattr(ticket, field, value)
            if details:
                changed_count += 1
                self.repo.session.add(
                    TicketActivity(
                        organization_id=organization_id,
                        ticket_id=ticket.id,
                        actor_user_id=actor_user_id,
                        activity_type="updated",
                        details=details,
                    )
                )
                if (
                    "assignee_id" in details
                    and ticket.assignee_id is not None
                    and ticket.assignee_id != actor_user_id
                ):
                    await enqueue_notification_event(
                        self.repo.session,
                        organization_id=organization_id,
                        event_type="ticket.assigned",
                        aggregate_type="ticket",
                        aggregate_id=ticket.id,
                        payload=TicketNotificationPayload(
                            ticket_id=ticket.id,
                            actor_user_id=actor_user_id,
                            recipient_user_id=ticket.assignee_id,
                            team_id=ticket.team_id,
                        ),
                    )

        await self.repo.session.flush()
        return changed_count, [ticket.id for ticket in tickets]

    async def _validate_team_assignment(
        self, organization_id: UUID, team_id: UUID, assignee_id: UUID | None
    ) -> None:
        team = await self.repo.session.scalar(
            select(Team).where(
                Team.organization_id == organization_id,
                Team.id == team_id,
                Team.is_active.is_(True),
            ).with_for_update()
        )
        if team is None:
            raise HTTPException(status_code=404, detail="Active team not found")
        if assignee_id is None:
            return
        membership = await self.repo.session.scalar(
            select(TeamMember.user_id).where(
                TeamMember.organization_id == organization_id,
                TeamMember.team_id == team_id,
                TeamMember.user_id == assignee_id,
            )
        )
        if membership is None:
            raise HTTPException(status_code=409, detail="The assignee must belong to the selected team")
