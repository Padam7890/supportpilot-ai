from sqlalchemy import func, or_, select

from app.models import Customer, Ticket
from app.repositories.base import TenantRepository


class CustomerRepository(TenantRepository[Customer]):
    def __init__(self, session):
        super().__init__(Customer, session)

    async def search_page(self, organization_id, *, search=None, limit=50, offset=0):
        conditions = [Customer.organization_id == organization_id]
        if search:
            term = f"%{search.strip()}%"
            conditions.append(or_(Customer.name.ilike(term), Customer.email.ilike(term)))
        count = await self.session.scalar(
            select(func.count()).select_from(Customer).where(*conditions)
        )
        rows = await self.session.execute(
            select(Customer)
            .where(*conditions)
            .order_by(Customer.created_at.desc(), Customer.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(count or 0)

    async def list_tickets(self, organization_id, customer_id, *, limit=50, offset=0):
        conditions = [Ticket.organization_id == organization_id, Ticket.customer_id == customer_id]
        count = await self.session.scalar(
            select(func.count()).select_from(Ticket).where(*conditions)
        )
        rows = await self.session.execute(
            select(Ticket)
            .where(*conditions)
            .order_by(Ticket.created_at.desc(), Ticket.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows.scalars().all()), int(count or 0)
