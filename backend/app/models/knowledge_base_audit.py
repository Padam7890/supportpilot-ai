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


class KnowledgeBaseAudit(UUIDPrimaryKey, Base):
    """Tenant-scoped history for knowledge-base and document-source changes."""

    __tablename__ = "knowledge_base_audits"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_knowledge_base_audits_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "knowledge_base_id"],
            ["knowledge_bases.organization_id", "knowledge_bases.id"],
            name="fk_knowledge_base_audits_org_base",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_knowledge_base_audits_org_actor",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "event_type IN ('created', 'updated', 'archived', 'restored', 'default_changed', 'document_moved')",
            name="ck_knowledge_base_audits_event_type",
        ),
        Index(
            "ix_knowledge_base_audits_org_base_time",
            "organization_id",
            "knowledge_base_id",
            "created_at",
            "id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
