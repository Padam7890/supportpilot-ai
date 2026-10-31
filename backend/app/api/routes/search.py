from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Customer, KnowledgeDocument, Ticket, User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.search import SearchResponse, SearchResultOut

router = APIRouter(prefix="/search", tags=["search"], responses=COMMON_ERROR_RESPONSES)


def escaped_search(value: str) -> str:
    escaped = value.replace("/", "//").replace("%", "/%").replace("_", "/_")
    return f"%{escaped}%"


@router.get("", response_model=SearchResponse)
async def command_search(
    q: str = Query(min_length=2, max_length=150),
    limit: int = Query(default=5, ge=1, le=10),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SearchResponse:
    term = escaped_search(q.strip())
    if len(q.strip()) < 2:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="Search query must have at least 2 characters")

    ticket_rows = await db.execute(
        select(Ticket, Customer.name)
        .join(
            Customer,
            (Customer.organization_id == Ticket.organization_id)
            & (Customer.id == Ticket.customer_id),
        )
        .where(
            Ticket.organization_id == user.organization_id,
            or_(
                Ticket.subject.ilike(term, escape="/"),
                Ticket.description.ilike(term, escape="/"),
                Customer.name.ilike(term, escape="/"),
                Customer.email.ilike(term, escape="/"),
            ),
        )
        .order_by(Ticket.updated_at.desc(), Ticket.id.desc())
        .limit(limit)
    )
    customer_rows = await db.scalars(
        select(Customer)
        .where(
            Customer.organization_id == user.organization_id,
            or_(Customer.name.ilike(term, escape="/"), Customer.email.ilike(term, escape="/")),
        )
        .order_by(Customer.updated_at.desc(), Customer.id.desc())
        .limit(limit)
    )
    document_rows = await db.scalars(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.organization_id == user.organization_id,
            KnowledgeDocument.deleted_at.is_(None),
            KnowledgeDocument.name.ilike(term, escape="/"),
        )
        .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
        .limit(limit)
    )
    items = [
        SearchResultOut(
            kind="ticket",
            id=ticket.id,
            title=ticket.subject,
            subtitle=f"{customer_name} · {ticket.status} ticket",
            href=f"/dashboard/tickets/{ticket.id}",
        )
        for ticket, customer_name in ticket_rows.all()
    ]
    items.extend(
        SearchResultOut(
            kind="customer",
            id=customer.id,
            title=customer.name,
            subtitle=customer.email,
            href=f"/dashboard/customers/{customer.id}",
        )
        for customer in customer_rows
    )
    items.extend(
        SearchResultOut(
            kind="document",
            id=document.id,
            title=document.name,
            subtitle=f"Knowledge document · {document.status}",
            href=f"/dashboard/knowledge/{document.id}",
        )
        for document in document_rows
    )
    return SearchResponse(query=q.strip(), items=items, limit_per_kind=limit)
