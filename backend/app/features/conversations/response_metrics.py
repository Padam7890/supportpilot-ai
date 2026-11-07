"""SQL expressions for customer-facing first replies."""

from sqlalchemy import func

from app.models import IntegrationDeliveryJob, Message


def first_reply_source():
    messages = Message.__table__
    deliveries = IntegrationDeliveryJob.__table__
    source = messages.outerjoin(
        deliveries,
        (deliveries.c.organization_id == messages.c.organization_id)
        & (deliveries.c.message_id == messages.c.id),
    )
    eligible = (
        messages.c.sender_type.in_(("agent", "assistant"))
        & messages.c.delivery_status.is_distinct_from("failed")
        & (
            deliveries.c.id.is_(None)
            | ((deliveries.c.status == "succeeded") & deliveries.c.completed_at.is_not(None))
        )
    )
    reply_at = func.greatest(messages.c.created_at, deliveries.c.completed_at)
    return source, eligible, reply_at
