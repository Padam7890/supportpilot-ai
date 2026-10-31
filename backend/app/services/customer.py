from uuid import UUID

from fastapi import HTTPException

from app.models import Customer
from app.repositories.customer import CustomerRepository
from app.schemas.customer import CustomerCreate, CustomerUpdate


class CustomerService:
    def __init__(self, repo: CustomerRepository):
        self.repo = repo

    async def create(self, organization_id: UUID, data: CustomerCreate):
        customer = Customer(organization_id=organization_id, **data.model_dump())
        return await self.repo.add(customer)

    async def get(self, organization_id: UUID, customer_id: UUID):
        customer = await self.repo.get(organization_id, customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")
        return customer

    async def list(self, organization_id: UUID, limit: int, offset: int):
        return await self.repo.list(organization_id, limit=limit, offset=offset)

    async def update(self, organization_id: UUID, customer_id: UUID, data: CustomerUpdate):
        customer = await self.get(organization_id, customer_id)
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(customer, key, value)
        await self.repo.session.flush()
        return customer
