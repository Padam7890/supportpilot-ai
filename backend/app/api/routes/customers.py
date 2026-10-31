from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import User
from app.repositories.customer import CustomerRepository
from app.schemas.customer import (
    CustomerCreate,
    CustomerOut,
    CustomerPage,
    CustomerUpdate,
)
from app.schemas.ticket import TicketPage
from app.services.customer import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"])


def service(db: AsyncSession) -> CustomerService:
    return CustomerService(CustomerRepository(db))


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    data: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> CustomerOut:
    return await service(db).create(user.organization_id, data)


@router.get("", response_model=CustomerPage)
async def list_customers(
    search: str | None = Query(default=None, max_length=160),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomerPage:
    items, total = await CustomerRepository(db).search_page(
        user.organization_id, search=search, limit=limit, offset=offset
    )
    return CustomerPage(items=items, total=total, limit=limit, offset=offset)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomerOut:
    return await service(db).get(user.organization_id, customer_id)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: UUID,
    data: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> CustomerOut:
    return await service(db).update(user.organization_id, customer_id, data)


@router.get("/{customer_id}/tickets", response_model=TicketPage)
async def customer_tickets(
    customer_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketPage:
    customer_service = service(db)
    await customer_service.get(user.organization_id, customer_id)
    items, total = await CustomerRepository(db).list_tickets(
        user.organization_id, customer_id, limit=limit, offset=offset
    )
    return TicketPage(items=items, total=total, limit=limit, offset=offset)
