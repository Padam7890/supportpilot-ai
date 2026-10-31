from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import Conversation, Message, Ticket, User
from app.repositories.customer import CustomerRepository
from app.schemas.customer import (
    CustomerCreate,
    CustomerMessageHistoryItem,
    CustomerMessageHistoryPage,
    CustomerOut,
    CustomerPage,
    CustomerUpdate,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.ticket import TicketPage
from app.services.customer import CustomerService

router = APIRouter(prefix="/customers", tags=["customers"], responses=COMMON_ERROR_RESPONSES)


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


@router.get("/{customer_id}/history", response_model=CustomerMessageHistoryPage)
async def customer_message_history(
    customer_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CustomerMessageHistoryPage:
    await service(db).get(user.organization_id, customer_id)
    conditions = (
        Ticket.organization_id == user.organization_id,
        Ticket.customer_id == customer_id,
        Conversation.organization_id == user.organization_id,
        Message.organization_id == user.organization_id,
        Message.sender_type != "internal_note",
    )
    total = int(
        await db.scalar(
            select(func.count(Message.id))
            .select_from(Message)
            .join(
                Conversation,
                and_(
                    Conversation.organization_id == Message.organization_id,
                    Conversation.id == Message.conversation_id,
                ),
            )
            .join(
                Ticket,
                and_(
                    Ticket.organization_id == Conversation.organization_id,
                    Ticket.id == Conversation.ticket_id,
                ),
            )
            .where(*conditions)
        )
        or 0
    )
    result = await db.execute(
        select(Message, Ticket.id, Ticket.subject, Conversation.id, User.full_name)
        .join(
            Conversation,
            and_(
                Conversation.organization_id == Message.organization_id,
                Conversation.id == Message.conversation_id,
            ),
        )
        .join(
            Ticket,
            and_(
                Ticket.organization_id == Conversation.organization_id,
                Ticket.id == Conversation.ticket_id,
            ),
        )
        .outerjoin(
            User,
            and_(User.organization_id == Message.organization_id, User.id == Message.sender_user_id),
        )
        .where(*conditions)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return CustomerMessageHistoryPage(
        items=[
            CustomerMessageHistoryItem(
                id=message.id,
                ticket_id=ticket_id,
                ticket_subject=subject,
                conversation_id=conversation_id,
                sender_type=message.sender_type,
                sender_name=sender_name,
                content=message.content,
                created_at=message.created_at,
            )
            for message, ticket_id, subject, conversation_id, sender_name in result.all()
        ],
        total=total,
        limit=limit,
        offset=offset,
    )
