import base64
import hashlib
import hmac
import json
import re
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import (
    Conversation,
    ConversationReadState,
    Customer,
    Message,
    Ticket,
    User,
)


def _filter_fingerprint(filters: dict[str, str | None]) -> str:
    encoded = json.dumps(filters, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _encode_cursor(
    *, updated_at: datetime, ticket_id: UUID, organization_id: UUID, user_id: UUID, fingerprint: str
) -> str:
    payload = json.dumps(
        {
            "updated_at": updated_at.isoformat(),
            "ticket_id": str(ticket_id),
            "organization_id": str(organization_id),
            "user_id": str(user_id),
            "filters": fingerprint,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(settings.jwt_secret.encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def _decode_cursor(
    token: str, *, organization_id: UUID, user_id: UUID, fingerprint: str
) -> tuple[datetime, UUID]:
    try:
        encoded, signature = token.split(".", 1)
        expected = hmac.new(
            settings.jwt_secret.encode(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid signature")
        payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
        if (
            payload["organization_id"] != str(organization_id)
            or payload["user_id"] != str(user_id)
            or payload["filters"] != fingerprint
        ):
            raise ValueError("cursor context mismatch")
        return datetime.fromisoformat(payload["updated_at"]), UUID(payload["ticket_id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Inbox cursor is invalid or expired") from None


class InboxRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_page(
        self,
        *,
        organization_id: UUID,
        user: User,
        scope: str,
        status: str | None,
        priority: str | None,
        search: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[dict], str | None]:
        filters = {
            "scope": scope,
            "status": status,
            "priority": priority,
            "search": search.strip().casefold() if search else None,
        }
        fingerprint = _filter_fingerprint(filters)

        latest_conversations = (
            select(
                Conversation.id.label("conversation_id"),
                Conversation.ticket_id.label("ticket_id"),
                Conversation.updated_at.label("conversation_updated_at"),
                func.row_number()
                .over(
                    partition_by=Conversation.ticket_id,
                    order_by=(
                        Conversation.updated_at.desc(),
                        Conversation.created_at.desc(),
                        Conversation.id.desc(),
                    ),
                )
                .label("conversation_rank"),
            )
            .where(Conversation.organization_id == organization_id)
            .subquery()
        )
        latest_messages = (
            select(
                Conversation.ticket_id.label("ticket_id"),
                Message.conversation_id.label("conversation_id"),
                Message.content.label("content"),
                Message.sender_type.label("sender_type"),
                Message.created_at.label("created_at"),
                func.row_number()
                .over(
                    partition_by=Conversation.ticket_id,
                    order_by=(Message.created_at.desc(), Message.id.desc()),
                )
                .label("message_rank"),
            )
            .join(
                Conversation,
                and_(
                    Conversation.id == Message.conversation_id,
                    Conversation.organization_id == Message.organization_id,
                ),
            )
            .where(
                Message.organization_id == organization_id,
                Message.sender_type != "internal_note",
            )
            .subquery()
        )
        read_state_join = and_(
            ConversationReadState.organization_id == organization_id,
            ConversationReadState.user_id == user.id,
            ConversationReadState.conversation_id == Conversation.id,
        )
        after_read_cursor = or_(
            ConversationReadState.user_id.is_(None),
            ConversationReadState.last_read_at.is_(None),
            tuple_(Message.created_at, Message.id)
            > tuple_(ConversationReadState.last_read_at, ConversationReadState.last_read_message_id),
        )
        unread_counts = (
            select(Conversation.ticket_id.label("ticket_id"), func.count(Message.id).label("unread_count"))
            .join(
                Message,
                and_(
                    Message.organization_id == Conversation.organization_id,
                    Message.conversation_id == Conversation.id,
                ),
            )
            .outerjoin(ConversationReadState, read_state_join)
            .where(
                Conversation.organization_id == organization_id,
                Message.sender_type == "customer",
                after_read_cursor,
            )
            .group_by(Conversation.ticket_id)
            .subquery()
        )

        activity_at = func.greatest(
            Ticket.updated_at,
            func.coalesce(latest_messages.c.created_at, Ticket.updated_at),
            func.coalesce(latest_conversations.c.conversation_updated_at, Ticket.updated_at),
        ).label("activity_at")
        conditions = [Ticket.organization_id == organization_id]
        if scope == "mine":
            conditions.append(Ticket.assignee_id == user.id)
        elif scope == "unassigned":
            conditions.append(Ticket.assignee_id.is_(None))
        if status:
            conditions.append(Ticket.status == status)
        if priority:
            conditions.append(Ticket.priority == priority)
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

        if cursor:
            cursor_updated_at, cursor_ticket_id = _decode_cursor(
                cursor,
                organization_id=organization_id,
                user_id=user.id,
                fingerprint=fingerprint,
            )
            conditions.append(
                or_(
                    activity_at < cursor_updated_at,
                    and_(activity_at == cursor_updated_at, Ticket.id < cursor_ticket_id),
                )
            )

        statement = (
            select(
                Ticket.id,
                Ticket.subject,
                Ticket.status,
                Ticket.priority,
                Customer.id.label("customer_id"),
                Customer.name.label("customer_name"),
                Customer.email.label("customer_email"),
                User.id.label("assignee_id"),
                User.full_name.label("assignee_name"),
                func.coalesce(
                    latest_messages.c.conversation_id,
                    latest_conversations.c.conversation_id,
                ).label("conversation_id"),
                latest_messages.c.content.label("latest_content"),
                latest_messages.c.created_at.label("latest_message_at"),
                latest_messages.c.sender_type.label("latest_sender_type"),
                func.coalesce(unread_counts.c.unread_count, 0).label("unread_count"),
                activity_at,
            )
            .join(
                Customer,
                and_(
                    Customer.id == Ticket.customer_id,
                    Customer.organization_id == Ticket.organization_id,
                ),
            )
            .outerjoin(
                User,
                and_(User.id == Ticket.assignee_id, User.organization_id == Ticket.organization_id),
            )
            .outerjoin(
                latest_conversations,
                and_(
                    latest_conversations.c.ticket_id == Ticket.id,
                    latest_conversations.c.conversation_rank == 1,
                ),
            )
            .outerjoin(
                latest_messages,
                and_(
                    latest_messages.c.ticket_id == Ticket.id,
                    latest_messages.c.message_rank == 1,
                ),
            )
            .outerjoin(unread_counts, unread_counts.c.ticket_id == Ticket.id)
            .where(*conditions)
            .order_by(activity_at.desc(), Ticket.id.desc())
            .limit(limit + 1)
        )
        result = await self.session.execute(statement)
        rows = list(result.mappings().all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        items = []
        for row in rows:
            preview = re.sub(r"\s+", " ", row["latest_content"] or "").strip()
            items.append(
                {
                    "ticket_id": row["id"],
                    "conversation_id": row["conversation_id"],
                    "subject": row["subject"],
                    "status": row["status"],
                    "priority": row["priority"],
                    "customer": {
                        "id": row["customer_id"],
                        "name": row["customer_name"],
                        "email": row["customer_email"],
                    },
                    "assignee": (
                        {"id": row["assignee_id"], "name": row["assignee_name"]}
                        if row["assignee_id"]
                        else None
                    ),
                    "latest_message": (
                        {
                            "preview": preview[:240],
                            "created_at": row["latest_message_at"],
                            "sender_type": row["latest_sender_type"],
                        }
                        if row["latest_message_at"]
                        else None
                    ),
                    "unread_count": int(row["unread_count"]),
                    "updated_at": row["activity_at"],
                }
            )

        next_cursor = None
        if has_more and rows:
            last = rows[-1]
            next_cursor = _encode_cursor(
                updated_at=last["activity_at"],
                ticket_id=last["id"],
                organization_id=organization_id,
                user_id=user.id,
                fingerprint=fingerprint,
            )
        return items, next_cursor
