"""Validated notification-domain events written into the transaction outbox."""

from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NotificationOutbox

EVENT_TYPES = (
    "ticket.assigned",
    "conversation.customer_replied",
    "ai.escalation_required",
)


class TicketNotificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticket_id: UUID
    conversation_id: UUID | None = None
    actor_user_id: UUID | None = None
    recipient_user_id: UUID | None = None
    team_id: UUID | None = None


async def enqueue_notification_event(
    db: AsyncSession,
    *,
    organization_id: UUID,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: TicketNotificationPayload,
    event_id: UUID | None = None,
) -> UUID:
    if event_type not in EVENT_TYPES:
        raise ValueError("Unsupported notification event")
    resolved_event_id = event_id or uuid4()
    await db.execute(
        insert(NotificationOutbox)
        .values(
            organization_id=organization_id,
            event_id=resolved_event_id,
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload.model_dump(mode="json"),
        )
        .on_conflict_do_nothing(constraint="uq_notification_outbox_org_event")
    )
    return resolved_event_id
