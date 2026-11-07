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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKey


class AIAgentAudit(UUIDPrimaryKey, Base):
    """Tenant-scoped audit history for safe AI bot configuration metadata."""

    __tablename__ = "ai_agent_audits"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_ai_agent_audits_org_id"),
        CheckConstraint(
            "event_type IN ('created', 'updated', 'knowledge_bases_changed', 'activated', 'deactivated')",
            name="ck_ai_agent_audits_event_type",
        ),
        CheckConstraint("config_version > 0", name="ck_ai_agent_audits_config_version"),
        ForeignKeyConstraint(
            ["organization_id", "ai_agent_id"],
            ["ai_agents.organization_id", "ai_agents.id"],
            name="fk_ai_agent_audits_org_agent",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ai_agent_audits_org_actor",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_ai_agent_audits_org_agent_time",
            "organization_id",
            "ai_agent_id",
            "created_at",
            "id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    ai_agent_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    config_version: Mapped[int] = mapped_column(nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
