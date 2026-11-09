"""Tenant- and recipient-scoped PostgreSQL notification queries."""

import base64
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.notifications.application.events import EVENT_TYPES
from app.models import Notification, NotificationOutbox, NotificationPreference, NotificationRecipient


def encode_cursor(created_at: datetime, notification_id: UUID) -> str:
    raw = f"{created_at.isoformat()}|{notification_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        timestamp, notification_id = raw.split("|", 1)
        created_at = datetime.fromisoformat(timestamp)
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)
        return created_at, UUID(notification_id)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid notification cursor") from exc


class NotificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_user(self, organization_id: UUID, user_id: UUID, *, limit: int, cursor: str | None, category: str | None, unread_only: bool):
        statement = (
            select(Notification, NotificationRecipient)
            .join(NotificationRecipient, and_(
                NotificationRecipient.organization_id == Notification.organization_id,
                NotificationRecipient.notification_id == Notification.id,
            ))
            .where(
                Notification.organization_id == organization_id,
                NotificationRecipient.organization_id == organization_id,
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.dismissed_at.is_(None),
            )
            .outerjoin(NotificationPreference, and_(
                NotificationPreference.organization_id == Notification.organization_id,
                NotificationPreference.user_id == NotificationRecipient.user_id,
                NotificationPreference.event_type == Notification.event_type,
            ))
            .where(or_(NotificationPreference.id.is_(None), NotificationPreference.in_app_enabled.is_(True)))
        )
        if category:
            statement = statement.where(Notification.category == category)
        if unread_only:
            statement = statement.where(NotificationRecipient.read_at.is_(None))
        if cursor:
            created_at, notification_id = decode_cursor(cursor)
            statement = statement.where(
                (Notification.created_at < created_at)
                | ((Notification.created_at == created_at) & (Notification.id < notification_id))
            )
        rows = list((await self.db.execute(statement.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1))).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = encode_cursor(rows[-1][0].created_at, rows[-1][0].id) if has_more and rows else None
        items = [
            {
                "id": notification.id,
                "event_type": notification.event_type,
                "category": notification.category,
                "priority": notification.priority,
                "title": notification.title,
                "body": notification.body,
                "resource_type": notification.resource_type,
                "resource_id": notification.resource_id,
                "action_url": notification.action_url,
                "created_at": notification.created_at,
                "read_at": recipient.read_at,
            }
            for notification, recipient in rows
        ]
        return items, next_cursor, has_more

    async def unread_count(self, organization_id: UUID, user_id: UUID) -> int:
        count = await self.db.scalar(
            select(func.count(NotificationRecipient.id))
            .join(Notification, and_(
                Notification.organization_id == NotificationRecipient.organization_id,
                Notification.id == NotificationRecipient.notification_id,
            ))
            .outerjoin(NotificationPreference, and_(
                NotificationPreference.organization_id == Notification.organization_id,
                NotificationPreference.user_id == NotificationRecipient.user_id,
                NotificationPreference.event_type == Notification.event_type,
            ))
            .where(
                NotificationRecipient.organization_id == organization_id,
                NotificationRecipient.user_id == user_id,
                NotificationRecipient.read_at.is_(None),
                NotificationRecipient.dismissed_at.is_(None),
                or_(NotificationPreference.id.is_(None), NotificationPreference.in_app_enabled.is_(True)),
            )
        )
        return int(count or 0)

    async def mark_read(self, organization_id: UUID, user_id: UUID, notification_id: UUID) -> bool:
        row = await self.db.scalar(select(NotificationRecipient).where(
            NotificationRecipient.organization_id == organization_id,
            NotificationRecipient.user_id == user_id,
            NotificationRecipient.notification_id == notification_id,
        ).with_for_update())
        if row is None:
            return False
        row.read_at = row.read_at or datetime.now(UTC)
        return True

    async def mark_all_read(self, organization_id: UUID, user_id: UUID, category: str | None) -> int:
        statement = update(NotificationRecipient).where(
            NotificationRecipient.organization_id == organization_id,
            NotificationRecipient.user_id == user_id,
            NotificationRecipient.read_at.is_(None),
            NotificationRecipient.dismissed_at.is_(None),
        )
        if category:
            statement = statement.where(NotificationRecipient.notification_id.in_(
                select(Notification.id).where(Notification.organization_id == organization_id, Notification.category == category)
            ))
        result = await self.db.execute(statement.values(read_at=datetime.now(UTC)))
        return int(result.rowcount or 0)

    async def dismiss(self, organization_id: UUID, user_id: UUID, notification_id: UUID) -> bool:
        row = await self.db.scalar(select(NotificationRecipient).where(
            NotificationRecipient.organization_id == organization_id,
            NotificationRecipient.user_id == user_id,
            NotificationRecipient.notification_id == notification_id,
        ).with_for_update())
        if row is None:
            return False
        row.dismissed_at = row.dismissed_at or datetime.now(UTC)
        return True

    async def get_preferences(self, organization_id: UUID, user_id: UUID):
        rows = await self.db.scalars(select(NotificationPreference).where(
            NotificationPreference.organization_id == organization_id,
            NotificationPreference.user_id == user_id,
        ))
        by_event = {row.event_type: row for row in rows}
        return [
            {
                "event_type": event_type,
                "in_app_enabled": by_event[event_type].in_app_enabled if event_type in by_event else True,
                "email_enabled": by_event[event_type].email_enabled if event_type in by_event else False,
            }
            for event_type in EVENT_TYPES
        ]

    async def update_preference(self, organization_id: UUID, user_id: UUID, event_type: str, *, in_app_enabled: bool | None, email_enabled: bool | None):
        statement = insert(NotificationPreference).values(
            organization_id=organization_id,
            user_id=user_id,
            event_type=event_type,
            in_app_enabled=True if in_app_enabled is None else in_app_enabled,
            email_enabled=False if email_enabled is None else email_enabled,
        )
        updates = {}
        if in_app_enabled is not None:
            updates["in_app_enabled"] = in_app_enabled
        if email_enabled is not None:
            updates["email_enabled"] = email_enabled
        if updates:
            statement = statement.on_conflict_do_update(
                constraint="uq_notification_preferences_user_event",
                set_={**updates, "updated_at": datetime.now(UTC)},
            )
        else:
            statement = statement.on_conflict_do_nothing(
                constraint="uq_notification_preferences_user_event"
            )
        await self.db.execute(statement)
        return await self.db.scalar(select(NotificationPreference).where(
            NotificationPreference.organization_id == organization_id,
            NotificationPreference.user_id == user_id,
            NotificationPreference.event_type == event_type,
        ))
