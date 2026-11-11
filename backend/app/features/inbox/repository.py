import base64
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.conversations.response_metrics import first_reply_source
from app.features.inbox.sla_policy import sla_target_minutes_expression
from app.models import (
    CommerceAction,
    Conversation,
    ConversationReadState,
    Customer,
    Message,
    Organization,
    Team,
    TeamMember,
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
        channel: str | None,
        team_id: UUID | None,
        needs_approval: bool,
        unread_only: bool,
        search: str | None,
        limit: int,
        cursor: str | None,
        overdue_only: bool = False,
        sla_status: str | None = None,
    ) -> tuple[list[dict], str | None]:
        normalized_search = search.strip() if search else ""
        filters = {
            "scope": scope,
            "status": status,
            "priority": priority,
            "team_id": str(team_id) if team_id else None,
            "needs_approval": str(needs_approval),
            "unread_only": str(unread_only),
            "search": normalized_search.casefold() or None,
        }
        effective_sla_status = sla_status or ("overdue" if overdue_only else None)
        filters["sla_status"] = effective_sla_status
        if channel:
            filters["channel"] = channel
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
        first_customer_messages = (
            select(
                Conversation.ticket_id.label("ticket_id"),
                func.min(Message.created_at).label("first_customer_at"),
            )
            .join(
                Message,
                and_(
                    Message.organization_id == Conversation.organization_id,
                    Message.conversation_id == Conversation.id,
                ),
            )
            .where(
                Conversation.organization_id == organization_id,
                Message.sender_type == "customer",
            )
            .group_by(Conversation.ticket_id)
            .cte("inbox_first_customer_message")
        )
        reply_source, reply_eligible, reply_at = first_reply_source()
        first_responses = (
            select(
                first_customer_messages.c.ticket_id,
                first_customer_messages.c.first_customer_at,
                func.min(reply_at).label("first_response_at"),
            )
            .select_from(
                first_customer_messages
                .join(
                    Conversation,
                    and_(
                        Conversation.organization_id == organization_id,
                        Conversation.ticket_id == first_customer_messages.c.ticket_id,
                    ),
                )
                .outerjoin(
                    reply_source,
                    and_(
                        Message.organization_id == Conversation.organization_id,
                        Message.conversation_id == Conversation.id,
                        Message.created_at > first_customer_messages.c.first_customer_at,
                        reply_eligible,
                    ),
                )
            )
            .group_by(first_customer_messages.c.ticket_id, first_customer_messages.c.first_customer_at)
            .cte("inbox_first_response")
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
        elif scope == "my_teams":
            member_team_ids = (
                select(TeamMember.team_id)
                .join(
                    Team,
                    and_(
                        Team.organization_id == TeamMember.organization_id,
                        Team.id == TeamMember.team_id,
                        Team.is_active.is_(True),
                    ),
                )
                .where(
                    TeamMember.organization_id == organization_id,
                    TeamMember.user_id == user.id,
                )
            )
            conditions.append(Ticket.team_id.in_(member_team_ids))
        if status:
            conditions.append(Ticket.status == status)
        if priority:
            conditions.append(Ticket.priority == priority)
        if channel:
            conditions.append(
                exists(
                    select(Conversation.id).where(
                        Conversation.organization_id == organization_id,
                        Conversation.ticket_id == Ticket.id,
                        Conversation.channel == channel,
                    )
                )
            )
        if team_id:
            conditions.append(Ticket.team_id == team_id)
        if needs_approval:
            conditions.append(
                exists(
                    select(CommerceAction.id).where(
                        CommerceAction.organization_id == organization_id,
                        CommerceAction.ticket_id == Ticket.id,
                        CommerceAction.approval_status == "pending",
                    )
                )
            )
        if unread_only:
            conditions.append(func.coalesce(unread_counts.c.unread_count, 0) > 0)
        if normalized_search:
            escaped_search = (
                normalized_search
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            term = f"%{escaped_search}%"
            conditions.append(
                or_(
                    Ticket.subject.ilike(term, escape="\\"),
                    Ticket.description.ilike(term, escape="\\"),
                    Customer.name.ilike(term, escape="\\"),
                    Customer.email.ilike(term, escape="\\"),
                    exists(
                        select(Message.id)
                        .join(
                            Conversation,
                            and_(
                                Conversation.id == Message.conversation_id,
                                Conversation.organization_id == Message.organization_id,
                            ),
                        )
                        .where(
                            Message.organization_id == organization_id,
                            Conversation.ticket_id == Ticket.id,
                            Message.sender_type != "internal_note",
                            Message.content.ilike(term, escape="\\"),
                        )
                    ),
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

        now = datetime.now(UTC)
        target_minutes = sla_target_minutes_expression(
            Organization.first_response_sla_minutes,
            Ticket.priority,
        )
        if effective_sla_status:
            first_customer_at = first_responses.c.first_customer_at
            first_response_at = first_responses.c.first_response_at
            elapsed_seconds = func.extract("epoch", now - first_customer_at)
            remaining_seconds = target_minutes * 60 - elapsed_seconds
            at_risk_threshold_seconds = func.least(60, func.greatest(5, target_minutes * 0.25)) * 60
            conditions.append(first_customer_at.is_not(None))
            if effective_sla_status == "met":
                conditions.extend((
                    first_response_at.is_not(None),
                    func.extract("epoch", first_response_at - first_customer_at) <= target_minutes * 60,
                ))
            elif effective_sla_status == "breached":
                conditions.extend((
                    first_response_at.is_not(None),
                    func.extract("epoch", first_response_at - first_customer_at) > target_minutes * 60,
                ))
            elif effective_sla_status == "overdue":
                conditions.extend((first_response_at.is_(None), elapsed_seconds >= target_minutes * 60))
            elif effective_sla_status == "at_risk":
                conditions.extend((
                    first_response_at.is_(None),
                    elapsed_seconds < target_minutes * 60,
                    remaining_seconds <= at_risk_threshold_seconds,
                ))
            else:
                conditions.extend((
                    first_response_at.is_(None),
                    remaining_seconds > at_risk_threshold_seconds,
                ))

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
                Team.id.label("team_id"),
                Team.name.label("team_name"),
                Team.is_active.label("team_is_active"),
                func.coalesce(
                    latest_messages.c.conversation_id,
                    latest_conversations.c.conversation_id,
                ).label("conversation_id"),
                latest_messages.c.content.label("latest_content"),
                latest_messages.c.created_at.label("latest_message_at"),
                latest_messages.c.sender_type.label("latest_sender_type"),
                first_responses.c.first_customer_at,
                first_responses.c.first_response_at,
                target_minutes.label("sla_target_minutes"),
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
            .join(Organization, Organization.id == Ticket.organization_id)
            .outerjoin(
                User,
                and_(User.id == Ticket.assignee_id, User.organization_id == Ticket.organization_id),
            )
            .outerjoin(
                Team,
                and_(Team.id == Ticket.team_id, Team.organization_id == Ticket.organization_id),
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
            .outerjoin(first_responses, first_responses.c.ticket_id == Ticket.id)
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
            sla = None
            first_customer_at = row["first_customer_at"]
            if first_customer_at is not None:
                target_minutes = row["sla_target_minutes"]
                due_at = first_customer_at + timedelta(minutes=target_minutes)
                response_at = row["first_response_at"]
                if response_at is not None:
                    sla_status = "met" if response_at <= due_at else "breached"
                elif now >= due_at:
                    sla_status = "overdue"
                elif due_at - now <= timedelta(minutes=min(60, max(5, target_minutes * 0.25))):
                    sla_status = "at_risk"
                else:
                    sla_status = "on_track"
                sla = {
                    "status": sla_status,
                    "target_minutes": target_minutes,
                    "due_at": due_at,
                    "responded_at": response_at,
                }
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
                    "team": (
                        {
                            "id": row["team_id"],
                            "name": row["team_name"],
                            "is_active": row["team_is_active"],
                        }
                        if row["team_id"]
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
                    "first_response_sla": sla,
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
