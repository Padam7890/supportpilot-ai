"""Tenant-safe message persistence and a transactional provider delivery outbox."""

import hashlib
import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.observability import current_correlation_id
from app.features.ai.application.defaults import get_default_agent
from app.features.automations.service import enqueue_customer_message_workflows
from app.features.notifications.application.events import (
    TicketNotificationPayload,
    enqueue_notification_event,
)
from app.integrations.core.contracts.messaging import IncomingMessage
from app.models import (
    AIAgent,
    Conversation,
    Customer,
    IntegrationConnection,
    IntegrationDeliveryJob,
    Message,
    Ticket,
)
from app.workers.domain.retry_policy import retry_delay_seconds as _retry_delay_seconds

logger = logging.getLogger(__name__)
MAX_DELIVERY_ATTEMPTS = 8
MAX_RETRY_SECONDS = 900


def retry_delay_seconds(
    attempt: int,
    *,
    retry_after_seconds: int | None = None,
    random_value: float | None = None,
) -> int:
    """Return bounded exponential backoff with full jitter."""
    return _retry_delay_seconds(
        attempt,
        base_seconds=2,
        cap_seconds=MAX_RETRY_SECONDS,
        retry_after_seconds=retry_after_seconds,
        random_value=random_value,
    )


def _idempotency_hash(message_id: UUID) -> str:
    return hashlib.sha256(f"integration-message:{message_id}".encode()).hexdigest()


async def enqueue_outbound_delivery(
    db: AsyncSession,
    *,
    organization_id: UUID,
    connection_id: UUID,
    message: Message,
) -> IntegrationDeliveryJob:
    """Atomically enqueue one outbound delivery for a persisted support message."""
    if message.organization_id != organization_id:
        raise ValueError("Message and delivery organization do not match")
    connection = await db.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.id == connection_id,
            IntegrationConnection.status == "connected",
        )
        .with_for_update()
    )
    if connection is None:
        raise ValueError("Connected provider connection was not found for this tenant")
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.organization_id == organization_id,
            Conversation.id == message.conversation_id,
            Conversation.integration_connection_id == connection_id,
        )
    )
    if conversation is None or message.sender_type not in {"agent", "assistant"}:
        raise ValueError("Only support replies for the linked conversation can be delivered")
    message.integration_connection_id = connection_id
    key_hash = _idempotency_hash(message.id)
    job_id = await db.scalar(
        pg_insert(IntegrationDeliveryJob)
        .values(
            organization_id=organization_id,
            connection_id=connection_id,
            message_id=message.id,
            idempotency_key_hash=key_hash,
            correlation_id=current_correlation_id(),
            status="queued",
            attempt_count=0,
            max_attempts=MAX_DELIVERY_ATTEMPTS,
            next_attempt_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing(constraint="uq_integration_delivery_jobs_message")
        .returning(IntegrationDeliveryJob.id)
    )
    if job_id is None:
        existing = await db.scalar(
            select(IntegrationDeliveryJob).where(
                IntegrationDeliveryJob.organization_id == organization_id,
                IntegrationDeliveryJob.message_id == message.id,
            )
        )
        if existing is None:
            raise RuntimeError("Delivery job conflict could not be resolved")
        return existing
    return await db.get(IntegrationDeliveryJob, job_id)


async def persist_incoming_message(
    db: AsyncSession,
    incoming: IncomingMessage,
) -> tuple[Message, bool]:
    """Idempotently append a normalized inbound message to its mapped conversation.

    Conversation mapping must be established by a trusted channel setup flow;
    external conversation identifiers never create tenant ownership by themselves.
    """
    if incoming.integration_connection_id is None:
        raise ValueError("Inbound provider messages require a connection")
    connection = await db.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.organization_id == incoming.organization_id,
            IntegrationConnection.id == incoming.integration_connection_id,
            IntegrationConnection.provider_id == incoming.provider_id,
            IntegrationConnection.status == "connected",
        )
        .with_for_update()
    )
    if connection is None:
        raise ValueError("Inbound provider connection is unavailable")
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.organization_id == incoming.organization_id,
            Conversation.integration_connection_id == connection.id,
            Conversation.external_conversation_id == incoming.external_conversation_id,
        )
    )
    ticket_created = conversation is None
    if conversation is None:
        sender_fingerprint = hashlib.sha256(
            f"{connection.id}:{incoming.external_sender_id}".encode()
        ).hexdigest()[:40]
        external_reference = f"integration:{connection.id}:{sender_fingerprint}"
        customer = await db.scalar(
            select(Customer).where(
                Customer.organization_id == incoming.organization_id,
                Customer.external_reference == external_reference,
            )
        )
        if customer is None:
            customer = Customer(
                organization_id=incoming.organization_id,
                name=incoming.sender_display_name or "Customer",
                email=f"external-{sender_fingerprint}@integration.invalid",
                external_reference=external_reference,
            )
            db.add(customer)
            await db.flush()
        first_line = " ".join(incoming.content.split())
        subject = first_line[:237].rstrip() + ("…" if len(first_line) > 237 else "")
        ticket = Ticket(
            organization_id=incoming.organization_id,
            customer_id=customer.id,
            subject=subject or "Integration support request",
            description=incoming.content,
            status="open",
            priority="normal",
            source="integration",
        )
        db.add(ticket)
        await db.flush()
        ai_agent = None
        if connection.ai_agent_id is not None:
            ai_agent = await db.scalar(
                select(AIAgent).where(
                    AIAgent.organization_id == incoming.organization_id,
                    AIAgent.id == connection.ai_agent_id,
                    AIAgent.status == "active",
                )
            )
        if ai_agent is None:
            ai_agent = await get_default_agent(db, incoming.organization_id)
        conversation = Conversation(
            organization_id=incoming.organization_id,
            ticket_id=ticket.id,
            channel="integration",
            status="active",
            integration_connection_id=connection.id,
            ai_agent_id=ai_agent.id,
            external_conversation_id=incoming.external_conversation_id,
        )
        db.add(conversation)
        await db.flush()
    message_id = await db.scalar(
        pg_insert(Message)
        .values(
            organization_id=incoming.organization_id,
            conversation_id=conversation.id,
            integration_connection_id=connection.id,
            sender_type="customer",
            sender_user_id=None,
            content=incoming.content,
            content_type=incoming.content_type,
            external_message_id=incoming.external_message_id,
            delivery_status="received",
            provider_metadata={
                "provider_id": incoming.provider_id,
                "attachments": [
                    {
                        "filename": item.filename,
                        "content_type": item.content_type,
                        "size_bytes": item.size_bytes,
                    }
                    for item in incoming.attachments
                ],
            },
            created_at=incoming.occurred_at,
        )
        .on_conflict_do_nothing(constraint="uq_messages_provider_external_id")
        .returning(Message.id)
    )
    if message_id is None:
        existing = await db.scalar(
            select(Message).where(
                Message.organization_id == incoming.organization_id,
                Message.integration_connection_id == connection.id,
                Message.external_message_id == incoming.external_message_id,
            )
        )
        if existing is None:
            raise RuntimeError("Inbound message conflict could not be resolved")
        if existing.conversation_id != conversation.id:
            raise ValueError("Provider message ID is already mapped to another conversation")
        return existing, False
    conversation.updated_at = max(conversation.updated_at, incoming.occurred_at)
    message = await db.get(Message, message_id)
    logger.info(
        "integration_inbound_message_persisted organization_id=%s connection_id=%s conversation_id=%s message_id=%s provider_id=%s",
        incoming.organization_id,
        connection.id,
        conversation.id,
        message_id,
        incoming.provider_id,
    )
    await enqueue_notification_event(
        db,
        organization_id=incoming.organization_id,
        event_type="conversation.customer_replied",
        aggregate_type="ticket",
        aggregate_id=conversation.ticket_id,
        event_id=message.id,
        payload=TicketNotificationPayload(ticket_id=conversation.ticket_id, conversation_id=conversation.id),
    )
    await enqueue_customer_message_workflows(
        db,
        organization_id=incoming.organization_id,
        ticket_id=conversation.ticket_id,
        conversation_id=conversation.id,
        message_id=message.id,
        ticket_created=ticket_created,
    )
    return message, True
