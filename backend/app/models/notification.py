import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKey


class Notification(UUIDPrimaryKey, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("organization_id", "event_id", name="uq_notifications_org_event"),
        UniqueConstraint("organization_id", "id", name="uq_notifications_org_id"),
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["organization_id", "actor_user_id"], ["users.organization_id", "users.id"], ondelete="RESTRICT", name="fk_notifications_org_actor"),
        Index("ix_notifications_org_created", "organization_id", "created_at"),
        Index("ix_notifications_org_category_created", "organization_id", "category", "created_at"),
        Index("uq_notifications_org_dedup", "organization_id", "deduplication_key", unique=True, postgresql_where=text("deduplication_key IS NOT NULL")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    resource_type: Mapped[str | None] = mapped_column(String(50))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    action_url: Mapped[str | None] = mapped_column(String(500))
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict, server_default=text("'{}'::jsonb"), nullable=False)
    deduplication_key: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


class NotificationRecipient(UUIDPrimaryKey, Base):
    __tablename__ = "notification_recipients"
    __table_args__ = (
        UniqueConstraint("notification_id", "user_id", name="uq_notification_recipients_notification_user"),
        ForeignKeyConstraint(["organization_id", "notification_id"], ["notifications.organization_id", "notifications.id"], ondelete="CASCADE", name="fk_notification_recipients_org_notification"),
        ForeignKeyConstraint(["organization_id", "user_id"], ["users.organization_id", "users.id"], ondelete="CASCADE", name="fk_notification_recipients_org_user"),
        Index("ix_notification_recipients_user_created", "organization_id", "user_id", "created_at"),
        Index("ix_notification_recipients_unread", "organization_id", "user_id", "created_at", postgresql_where=text("read_at IS NULL AND dismissed_at IS NULL")),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    notification_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    email_attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    email_last_error: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


class NotificationPreference(UUIDPrimaryKey, Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "event_type", name="uq_notification_preferences_user_event"),
        ForeignKeyConstraint(["organization_id", "user_id"], ["users.organization_id", "users.id"], ondelete="CASCADE", name="fk_notification_preferences_org_user"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    in_app_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"), nullable=False)
    email_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)


class NotificationOutbox(UUIDPrimaryKey, Base):
    __tablename__ = "notification_outbox"
    __table_args__ = (
        UniqueConstraint("organization_id", "event_id", name="uq_notification_outbox_org_event"),
        ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        CheckConstraint("attempt_count >= 0", name="ck_notification_outbox_attempt_count"),
        CheckConstraint("status IN ('pending', 'running', 'completed', 'failed')", name="ck_notification_outbox_status"),
        Index("ix_notification_outbox_claim", "organization_id", "status", "next_attempt_at", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
