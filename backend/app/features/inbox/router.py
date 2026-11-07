from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.features.inbox.repository import InboxRepository
from app.models import Conversation, ConversationReadState, Message, User
from app.schemas.conversation import ConversationReadOut, InboxItemOut, InboxPage
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(tags=["inbox"], responses=COMMON_ERROR_RESPONSES)


@router.get("/inbox", response_model=InboxPage)
async def list_inbox(
    scope: str = Query(default="all", pattern="^(all|mine|unassigned|my_teams)$"),
    status: str | None = Query(default=None, pattern="^(open|pending|resolved|closed)$"),
    priority: str | None = Query(default=None, pattern="^(low|normal|high|urgent)$"),
    team_id: UUID | None = Query(default=None),
    needs_approval: bool = False,
    unread_only: bool = False,
    overdue_only: bool = False,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=2048),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> InboxPage:
    items, next_cursor = await InboxRepository(db).search_page(
        organization_id=user.organization_id,
        user=user,
        scope=scope,
        status=status,
        priority=priority,
        team_id=team_id,
        needs_approval=needs_approval,
        unread_only=unread_only,
        overdue_only=overdue_only,
        search=search,
        limit=limit,
        cursor=cursor,
    )
    return InboxPage(
        items=[InboxItemOut.model_validate(item) for item in items],
        limit=limit,
        next_cursor=next_cursor,
    )


@router.post("/conversations/{conversation_id}/read", response_model=ConversationReadOut)
async def mark_conversation_read(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationReadOut:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == user.organization_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    latest = await db.execute(
        select(Message.id, Message.created_at)
        .where(
            Message.organization_id == user.organization_id,
            Message.conversation_id == conversation_id,
        )
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(1)
    )
    row = latest.one_or_none()
    if row is None:
        return ConversationReadOut(
            conversation_id=conversation_id,
            last_read_at=None,
            last_read_message_id=None,
        )

    now = datetime.now(UTC)
    table = ConversationReadState.__table__
    excluded = insert(table).excluded
    stmt = insert(table).values(
        organization_id=user.organization_id,
        user_id=user.id,
        conversation_id=conversation_id,
        last_read_at=row.created_at,
        last_read_message_id=row.id,
        updated_at=now,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.organization_id, table.c.user_id, table.c.conversation_id],
        set_={
            "last_read_at": excluded.last_read_at,
            "last_read_message_id": excluded.last_read_message_id,
            "updated_at": excluded.updated_at,
        },
        where=tuple_(excluded.last_read_at, excluded.last_read_message_id)
        > tuple_(table.c.last_read_at, table.c.last_read_message_id),
    )
    await db.execute(stmt)
    return ConversationReadOut(
        conversation_id=conversation_id,
        last_read_at=row.created_at,
        last_read_message_id=row.id,
    )
