from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.models import Customer, Ticket, TicketLink
from app.repositories.base import TenantRepository


class TicketRepository(TenantRepository[Ticket]):
    def __init__(self, session):
        super().__init__(Ticket, session)

    async def get(self, organization_id, record_id):
        result = await self.session.execute(
            select(Ticket)
            .options(selectinload(Ticket.customer), selectinload(Ticket.assignee), selectinload(Ticket.team))
            .where(Ticket.id == record_id, Ticket.organization_id == organization_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_locked(self, organization_id, record_id):
        result = await self.session.execute(
            select(Ticket)
            .options(selectinload(Ticket.customer), selectinload(Ticket.assignee), selectinload(Ticket.team))
            .where(Ticket.id == record_id, Ticket.organization_id == organization_id)
            .with_for_update(of=Ticket)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def exists(self, organization_id, record_id) -> bool:
        """Check tenant ownership without loading customer or assignee relationships."""
        ticket_id = await self.session.scalar(
            select(Ticket.id).where(
                Ticket.id == record_id,
                Ticket.organization_id == organization_id,
            )
        )
        return ticket_id is not None

    async def lock_many(self, organization_id, ticket_ids):
        """Lock only the requested tickets owned by this organization."""
        result = await self.session.scalars(
            select(Ticket)
            .where(
                Ticket.organization_id == organization_id,
                Ticket.id.in_(ticket_ids),
            )
            .order_by(Ticket.id)
            .with_for_update()
        )
        return list(result.all())

    async def search_page(
        self,
        organization_id,
        *,
        search=None,
        status=None,
        priority=None,
        assignee_id=None,
        customer_id=None,
        limit=50,
        offset=0,
    ):
        conditions = [Ticket.organization_id == organization_id]
        if search:
            term = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Ticket.subject.ilike(term),
                    Ticket.description.ilike(term),
                    Customer.name.ilike(term),
                    Customer.email.ilike(term),
                )
            )
        if status:
            conditions.append(Ticket.status == status)
        if priority:
            conditions.append(Ticket.priority == priority)
        if assignee_id:
            conditions.append(Ticket.assignee_id == assignee_id)
        if customer_id:
            conditions.append(Ticket.customer_id == customer_id)
        base = select(Ticket).join(Customer, Ticket.customer_id == Customer.id).where(*conditions)
        count = await self.session.scalar(
            select(func.count(Ticket.id))
            .select_from(Ticket)
            .join(Customer, Ticket.customer_id == Customer.id)
            .where(*conditions)
        )
        rows = await self.session.execute(
            base.options(selectinload(Ticket.customer), selectinload(Ticket.assignee), selectinload(Ticket.team))
            .order_by(Ticket.created_at.desc(), Ticket.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(count or 0)

    async def search_link_candidates(
        self,
        organization_id,
        ticket_id,
        *,
        search,
        limit=10,
        offset=0,
    ):
        existing_link = select(TicketLink.id).where(
            TicketLink.organization_id == organization_id,
            or_(
                and_(
                    TicketLink.ticket_low_id == ticket_id,
                    TicketLink.ticket_high_id == Ticket.id,
                ),
                and_(
                    TicketLink.ticket_high_id == ticket_id,
                    TicketLink.ticket_low_id == Ticket.id,
                ),
            ),
        ).exists()
        conditions = [
            Ticket.organization_id == organization_id,
            Ticket.id != ticket_id,
            ~existing_link,
        ]
        if search:
            term = f"%{search.strip()}%"
            conditions.append(
                or_(
                    Ticket.subject.ilike(term),
                    Ticket.description.ilike(term),
                    Customer.name.ilike(term),
                    Customer.email.ilike(term),
                )
            )
        count = await self.session.scalar(
            select(func.count(Ticket.id))
            .select_from(Ticket)
            .join(Customer, Ticket.customer_id == Customer.id)
            .where(*conditions)
        )
        rows = await self.session.execute(
            select(Ticket)
            .join(Customer, Ticket.customer_id == Customer.id)
            .options(selectinload(Ticket.customer), selectinload(Ticket.assignee), selectinload(Ticket.team))
            .where(*conditions)
            .order_by(Ticket.created_at.desc(), Ticket.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(count or 0)
