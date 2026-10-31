from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.models import Customer, Ticket
from app.repositories.base import TenantRepository


class TicketRepository(TenantRepository[Ticket]):
    def __init__(self, session):
        super().__init__(Ticket, session)

    async def get(self, organization_id, record_id):
        result = await self.session.execute(
            select(Ticket)
            .options(selectinload(Ticket.customer), selectinload(Ticket.assignee))
            .where(Ticket.id == record_id, Ticket.organization_id == organization_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

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
            base.options(selectinload(Ticket.customer), selectinload(Ticket.assignee))
            .order_by(Ticket.created_at.desc(), Ticket.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(count or 0)
