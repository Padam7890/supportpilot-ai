"""Tenant-owned provider connections and encrypted credential records."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class IntegrationConnection(UUIDPrimaryKey, TimestampMixin, Base):
    """A tenant's account-level connection to an integration provider."""

    __tablename__ = "integration_connections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'connected', 'disconnected', 'error', 'reauthorization_required')",
            name="ck_integration_connections_status",
        ),
        UniqueConstraint(
            "organization_id",
            "provider_id",
            "external_account_id",
            name="uq_integration_connections_org_provider_account",
        ),
        UniqueConstraint("organization_id", "id", name="uq_integration_connections_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "connected_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_integration_connections_org_user",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_integration_connections_org_provider_status",
            "organization_id",
            "provider_id",
            "status",
        ),
        Index("ix_integration_connections_health", "status", "last_checked_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[str] = mapped_column(String(48), nullable=False)
    external_account_id: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    safe_configuration: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    connected_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))

    credentials = relationship(
        "IntegrationCredential", back_populates="connection", cascade="all, delete-orphan"
    )


class IntegrationCredential(UUIDPrimaryKey, TimestampMixin, Base):
    """Encrypted credential material. Never serialize this model into an API response."""

    __tablename__ = "integration_credentials"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connection_id",
            "credential_type",
            name="uq_integration_credentials_connection_type",
        ),
        ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_integration_credentials_org_connection",
            ondelete="CASCADE",
        ),
        Index("ix_integration_credentials_expiry", "organization_id", "expires_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    credential_type: Mapped[str] = mapped_column(String(48), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[str] = mapped_column(String(48), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    connection = relationship("IntegrationConnection", back_populates="credentials")

    @staticmethod
    def now() -> datetime:
        return datetime.now(UTC)


class IntegrationWebhookEvent(UUIDPrimaryKey, TimestampMixin, Base):
    """Verified, minimized webhook envelope used for durable deduplication."""

    __tablename__ = "integration_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "connection_id",
            "provider_id",
            "external_event_id",
            name="uq_integration_webhook_events_dedupe",
        ),
        ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_integration_webhook_events_org_connection",
            ondelete="CASCADE",
        ),
        Index(
            "ix_integration_webhook_events_org_created",
            "organization_id",
            "created_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(48), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(512), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class IntegrationDeliveryJob(UUIDPrimaryKey, TimestampMixin, Base):
    """Transactional outbox row for outbound provider message delivery."""

    __tablename__ = "integration_delivery_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_integration_delivery_jobs_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts",
            name="ck_integration_delivery_jobs_attempts",
        ),
        CheckConstraint("max_attempts > 0", name="ck_integration_delivery_jobs_max_attempts"),
        UniqueConstraint(
            "organization_id", "idempotency_key_hash", name="uq_integration_delivery_jobs_idempotency"
        ),
        UniqueConstraint(
            "organization_id", "message_id", name="uq_integration_delivery_jobs_message"
        ),
        ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_integration_delivery_jobs_org_connection",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "message_id"],
            ["messages.organization_id", "messages.id"],
            name="fk_integration_delivery_jobs_org_message",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "message_id", "connection_id"],
            [
                "messages.organization_id",
                "messages.id",
                "messages.integration_connection_id",
            ],
            name="fk_integration_delivery_jobs_message_connection",
            ondelete="CASCADE",
        ),
        Index(
            "ix_integration_delivery_jobs_queue",
            "organization_id",
            "status",
            "next_attempt_at",
            "created_at",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    provider_message_id: Mapped[str | None] = mapped_column(String(512))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
