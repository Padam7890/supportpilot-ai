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
