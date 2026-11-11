"""Durable, tenant-scoped notification outbox delivery."""

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.db.session import SessionLocal, set_tenant_context
from app.features.notifications.application.events import TicketNotificationPayload
from app.models import (
    Conversation,
    Notification,
    NotificationOutbox,
    NotificationPreference,
    NotificationRecipient,
    TeamMember,
    Ticket,
    User,
)
from app.services.email_delivery import send_notification_email
from app.workers.domain.retry_policy import retry_delay_seconds

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 8
LEASE = timedelta(minutes=2)


async def claim_notification_outbox(organization_id: UUID) -> UUID | None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        row = await db.scalar(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.organization_id == organization_id,
                NotificationOutbox.attempt_count < MAX_ATTEMPTS,
                or_(
                    and_(NotificationOutbox.status == "pending", or_(NotificationOutbox.next_attempt_at.is_(None), NotificationOutbox.next_attempt_at <= now)),
                    and_(
                        NotificationOutbox.status == "running",
                        or_(
                            NotificationOutbox.locked_until.is_(None),
                            NotificationOutbox.locked_until <= now,
                        ),
                    ),
                ),
            )
            .order_by(NotificationOutbox.created_at, NotificationOutbox.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if row is None:
            await db.rollback()
            return None
        row.status = "running"
        row.attempt_count += 1
        row.locked_until = now + LEASE
        job_id = row.id
        await db.commit()
        return job_id


async def _recipients(
    db,
    organization_id: UUID,
    event_type: str,
    payload: TicketNotificationPayload,
) -> list[UUID]:
    ticket = await db.scalar(select(Ticket).where(
        Ticket.organization_id == organization_id,
        Ticket.id == payload.ticket_id,
    ))
    if ticket is None:
        return []
    if event_type == "conversation.customer_replied":
        if payload.conversation_id is None:
            return []
        conversation = await db.scalar(select(Conversation).where(
            Conversation.organization_id == organization_id,
            Conversation.id == payload.conversation_id,
            Conversation.ticket_id == ticket.id,
        ))
        # Human takeover and active conversations are the only customer replies
        # that should create teammate alerts. AI-owned/closed threads continue
        # to be visible in the inbox without generating a redundant alert.
        if conversation is None or conversation.ai_mode != "human" or conversation.status != "active":
            return []
    if payload.recipient_user_id:
        recipient = await db.scalar(select(User.id).where(
            User.organization_id == organization_id,
            User.id == payload.recipient_user_id,
            User.is_active.is_(True),
        ))
        return [] if recipient is None or recipient == payload.actor_user_id else [recipient]
    if ticket.assignee_id and ticket.assignee_id != payload.actor_user_id:
        assignee = await db.scalar(select(User.id).where(
            User.organization_id == organization_id,
            User.id == ticket.assignee_id,
            User.is_active.is_(True),
        ))
        if assignee is not None:
            return [assignee]
    if ticket.team_id:
        member_ids = list(await db.scalars(select(TeamMember.user_id).where(
            TeamMember.organization_id == organization_id,
            TeamMember.team_id == ticket.team_id,
        TeamMember.user_id.in_(select(User.id).where(
            User.organization_id == organization_id,
            User.is_active.is_(True),
        )),
        )))
        if member_ids:
            return sorted(set(member_ids) - ({payload.actor_user_id} if payload.actor_user_id else set()))
    fallback = list(await db.scalars(select(User.id).where(
        User.organization_id == organization_id,
        User.is_active.is_(True),
        User.role.in_(("owner", "admin")),
    )))
    return sorted(set(fallback) - ({payload.actor_user_id} if payload.actor_user_id else set()))


def _content(event_type: str, ticket: Ticket) -> tuple[str, str, str, str]:
    if event_type == "ticket.assigned":
        return "team", "Ticket assigned to you", ticket.subject, "high"
    if event_type == "conversation.customer_replied":
        return "inbox", "New customer reply", ticket.subject, "normal"
    return "ai", "AI needs a human", ticket.subject, "high"


async def _publish(organization_id: UUID, recipients: list[UUID], notification_id: UUID) -> None:
    if not recipients:
        return
    client = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        data = json.dumps({"notification_id": str(notification_id)})
        for user_id in recipients:
            await client.publish(f"supportpilot:notifications:{organization_id}:{user_id}", data)
    finally:
        await client.aclose()


async def process_notification_outbox(organization_id: UUID, job_id: UUID) -> None:
    now = datetime.now(UTC)
    published_id: UUID | None = None
    published_recipients: list[UUID] = []
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        outbox = await db.scalar(select(NotificationOutbox).where(
            NotificationOutbox.organization_id == organization_id,
            NotificationOutbox.id == job_id,
            NotificationOutbox.status == "running",
        ).with_for_update())
        if outbox is None:
            return
        try:
            payload = TicketNotificationPayload.model_validate(outbox.payload)
            ticket = await db.scalar(select(Ticket).where(
                Ticket.organization_id == organization_id,
                Ticket.id == payload.ticket_id,
            ))
            if ticket is None:
                outbox.status = "completed"
                outbox.processed_at = now
                outbox.locked_until = None
                await db.commit()
                return
            recipient_ids = await _recipients(db, organization_id, outbox.event_type, payload)
            if not recipient_ids:
                outbox.status = "completed"
                outbox.processed_at = now
                outbox.locked_until = None
                await db.commit()
                return

            category, title, body, priority = _content(outbox.event_type, ticket)
            notification_id = await db.scalar(
                insert(Notification)
                .values(
                    organization_id=organization_id,
                    event_id=outbox.event_id,
                    event_type=outbox.event_type,
                    category=category,
                    priority=priority,
                    title=title,
                    body=body,
                    actor_user_id=payload.actor_user_id,
                    resource_type="ticket",
                    resource_id=ticket.id,
                    action_url=f"/dashboard/tickets/{ticket.id}",
                    deduplication_key=f"{outbox.event_type}:{outbox.event_id}",
                )
                .on_conflict_do_nothing(constraint="uq_notifications_org_event")
                .returning(Notification.id)
            )
            if notification_id is None:
                notification_id = await db.scalar(select(Notification.id).where(
                    Notification.organization_id == organization_id,
                    Notification.event_id == outbox.event_id,
                ))
            if notification_id is None:
                raise RuntimeError("notification_persist_failed")
            preferences = await db.execute(select(NotificationPreference, User).join(
                User, and_(User.organization_id == NotificationPreference.organization_id, User.id == NotificationPreference.user_id)
            ).where(
                NotificationPreference.organization_id == organization_id,
                NotificationPreference.user_id.in_(recipient_ids),
                NotificationPreference.event_type == outbox.event_type,
            ))
            preference_by_user = {pref.user_id: (pref, user) for pref, user in preferences.all()}
            enabled_recipients = []
            email_delivery_failed = False
            for user_id in recipient_ids:
                pref_user = preference_by_user.get(user_id)
                if pref_user is None:
                    user = await db.scalar(select(User).where(User.organization_id == organization_id, User.id == user_id))
                    if user is None:
                        continue
                    pref = None
                else:
                    pref, user = pref_user
                in_app_enabled = pref.in_app_enabled if pref else True
                email_enabled = pref.email_enabled if pref else False
                if not in_app_enabled and not email_enabled:
                    continue
                await db.execute(insert(NotificationRecipient).values(
                    organization_id=organization_id,
                    notification_id=notification_id,
                    user_id=user_id,
                ).on_conflict_do_nothing(constraint="uq_notification_recipients_notification_user"))
                recipient = await db.scalar(select(NotificationRecipient).where(
                    NotificationRecipient.organization_id == organization_id,
                    NotificationRecipient.notification_id == notification_id,
                    NotificationRecipient.user_id == user_id,
                ).with_for_update())
                if in_app_enabled:
                    enabled_recipients.append(user_id)
                if email_enabled and user.email and recipient and recipient.email_sent_at is None:
                    recipient.email_attempt_count += 1
                    try:
                        await send_notification_email(user.email, title, body, f"/dashboard/tickets/{ticket.id}")
                        recipient.email_sent_at = datetime.now(UTC)
                        recipient.email_last_error = None
                    except Exception as exc:  # noqa: BLE001 - retry failed email delivery
                        recipient.email_last_error = type(exc).__name__[:80]
                        email_delivery_failed = True
                        logger.warning(
                            "notification_email_delivery_retry",
                            extra={
                                "organization_id": str(organization_id),
                                "job_id": str(job_id),
                                "recipient_id": str(user_id),
                                "error_type": type(exc).__name__,
                            },
                        )
            outbox.status = (
                "pending"
                if email_delivery_failed and outbox.attempt_count < MAX_ATTEMPTS
                else "failed"
                if email_delivery_failed
                else "completed"
            )
            outbox.next_attempt_at = (
                datetime.now(UTC) + timedelta(seconds=retry_delay_seconds(outbox.attempt_count))
                if email_delivery_failed and outbox.attempt_count < MAX_ATTEMPTS
                else None
            )
            outbox.processed_at = now if outbox.status == "completed" else None
            outbox.locked_until = None
            outbox.last_error = "notification_email_delivery_failed" if email_delivery_failed else None
            await db.commit()
            published_id = notification_id
            published_recipients = enabled_recipients
            if email_delivery_failed and outbox.status == "failed":
                logger.error(
                    "notification_outbox_dead_letter",
                    extra={"organization_id": str(organization_id), "job_id": str(job_id)},
                )
        except Exception as exc:  # noqa: BLE001 - persist a retry or dead letter for the job
            await db.rollback()
            await set_tenant_context(db, organization_id)
            failed = await db.scalar(select(NotificationOutbox).where(
                NotificationOutbox.organization_id == organization_id,
                NotificationOutbox.id == job_id,
            ).with_for_update())
            if failed is not None:
                failed.locked_until = None
                failed.last_error = f"notification_delivery_failed:{type(exc).__name__}"[:160]
                if failed.attempt_count >= MAX_ATTEMPTS:
                    failed.status = "failed"
                    logger.error("notification_outbox_dead_letter", extra={"organization_id": str(organization_id), "job_id": str(job_id), "error_type": type(exc).__name__})
                else:
                    failed.status = "pending"
                    failed.next_attempt_at = datetime.now(UTC) + timedelta(seconds=retry_delay_seconds(failed.attempt_count))
                await db.commit()
            logger.warning("notification_outbox_delivery_retry", extra={"organization_id": str(organization_id), "job_id": str(job_id), "error_type": type(exc).__name__})
            return
    if published_id:
        try:
            await _publish(organization_id, published_recipients, published_id)
        except Exception as exc:  # noqa: BLE001 - fanout is best effort after persistence
            logger.warning("notification_fanout_failed", extra={"organization_id": str(organization_id), "error_type": type(exc).__name__})
