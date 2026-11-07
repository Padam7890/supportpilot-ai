"""Tenant-scoped first-response SLA aggregates for Analytics."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import and_, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.conversations.response_metrics import first_reply_source
from app.features.inbox.sla_policy import sla_target_minutes_expression
from app.models import Conversation, Message, Organization, Ticket
from app.schemas.analytics import FirstResponseSLAAnalytics


async def get_first_response_sla_analytics(
    db: AsyncSession,
    *,
    organization_id: UUID,
    start: date,
    end: date,
) -> FirstResponseSLAAnalytics:
    """Count ticket-level SLA outcomes using the same accepted-reply rule as Inbox."""
    first_customer = (
        select(
            Conversation.organization_id.label("organization_id"),
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
        .group_by(Conversation.organization_id, Conversation.ticket_id)
        .cte("sla_first_customer_by_ticket")
    )
    response_messages = Message.__table__
    response_source, reply_eligible, response_at = first_reply_source()
    period_start = datetime.combine(start, time.min, tzinfo=UTC)
    period_end = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    ticket_responses = (
        select(
            first_customer.c.organization_id,
            first_customer.c.ticket_id,
            first_customer.c.first_customer_at,
            func.min(response_at).label("first_response_at"),
        )
        .select_from(
            first_customer.join(
                Conversation,
                and_(
                    Conversation.organization_id == first_customer.c.organization_id,
                    Conversation.ticket_id == first_customer.c.ticket_id,
                ),
            ).outerjoin(
                response_source,
                and_(
                    response_messages.c.organization_id == Conversation.organization_id,
                    response_messages.c.conversation_id == Conversation.id,
                    response_messages.c.created_at > first_customer.c.first_customer_at,
                    reply_eligible,
                ),
            )
        )
        .where(
            first_customer.c.organization_id == organization_id,
            first_customer.c.first_customer_at >= period_start,
            first_customer.c.first_customer_at < period_end,
        )
        .group_by(
            first_customer.c.organization_id,
            first_customer.c.ticket_id,
            first_customer.c.first_customer_at,
        )
        .cte("sla_first_response_by_ticket")
    )
    now = datetime.now(UTC)
    target_minutes = sla_target_minutes_expression(
        Organization.first_response_sla_minutes,
        Ticket.priority,
    )
    response_seconds = extract(
        "epoch", ticket_responses.c.first_response_at - ticket_responses.c.first_customer_at
    )
    remaining_seconds = (
        extract("epoch", ticket_responses.c.first_customer_at - now) + target_minutes * 60
    )
    at_risk_threshold = func.least(60, func.greatest(5, target_minutes * 0.25)) * 60
    waiting = ticket_responses.c.first_response_at.is_(None)

    row = await db.execute(
        select(
            func.count(ticket_responses.c.ticket_id),
            func.count(ticket_responses.c.ticket_id).filter(
                ticket_responses.c.first_response_at.is_not(None)
                & (response_seconds <= target_minutes * 60)
            ),
            func.count(ticket_responses.c.ticket_id).filter(
                ticket_responses.c.first_response_at.is_not(None)
                & (response_seconds > target_minutes * 60)
            ),
            func.count(ticket_responses.c.ticket_id).filter(waiting),
            func.count(ticket_responses.c.ticket_id).filter(
                waiting & (remaining_seconds <= 0)
            ),
            func.count(ticket_responses.c.ticket_id).filter(
                waiting
                & (remaining_seconds > 0)
                & (remaining_seconds <= at_risk_threshold)
            ),
            func.count(ticket_responses.c.ticket_id).filter(
                waiting & (remaining_seconds > at_risk_threshold)
            ),
        )
        .select_from(
            ticket_responses.join(
                Ticket,
                and_(
                    Ticket.organization_id == ticket_responses.c.organization_id,
                    Ticket.id == ticket_responses.c.ticket_id,
                ),
            ).join(Organization, Organization.id == ticket_responses.c.organization_id)
        )
        .where(Ticket.organization_id == organization_id)
    )
    total, met, breached, awaiting, overdue, at_risk, on_track = row.one()
    replied = int(met or 0) + int(breached or 0)
    return FirstResponseSLAAnalytics(
        tickets=int(total or 0),
        met=int(met or 0),
        breached=int(breached or 0),
        awaiting= int(awaiting or 0),
        overdue=int(overdue or 0),
        at_risk=int(at_risk or 0),
        on_track=int(on_track or 0),
        compliance_rate=(round(int(met or 0) / replied * 100, 2) if replied else None),
    )
