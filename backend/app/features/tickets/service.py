from uuid import UUID

from fastapi import HTTPException

from app.features.customers.repository import CustomerRepository
from app.features.tickets.repository import TicketRepository
from app.models import Ticket, TicketActivity
from app.schemas.ticket import TicketCreate, TicketUpdate


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

    async def list(self, organization_id: UUID, limit: int, offset: int):
        return await self.repo.list(organization_id, limit=limit, offset=offset)

    async def update(
        self,
        organization_id: UUID,
        ticket_id: UUID,
        data: TicketUpdate,
        actor_user_id: UUID | None = None,
    ):
        ticket = await self.get(organization_id, ticket_id)
        changes = data.model_dump(exclude_unset=True)
        if "assignee_id" in changes and changes["assignee_id"] is not None:
            from sqlalchemy import select

            from app.models import User

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
        return await self.repo.get(organization_id, ticket_id)
