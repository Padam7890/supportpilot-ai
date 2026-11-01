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
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class AIExecution(UUIDPrimaryKey, TimestampMixin, Base):
    """Tenant-owned durable job plus the safe result fields returned by APIs."""

    __tablename__ = "ai_executions"
    __table_args__ = (
        CheckConstraint("kind IN ('playground', 'reply_draft', 'widget_reply', 'recommendation')", name="ck_ai_executions_kind"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_ai_executions_status",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts",
            name="ck_ai_executions_attempt_count",
        ),
        CheckConstraint("max_attempts > 0", name="ck_ai_executions_max_attempts"),
        CheckConstraint("delivery_mode IS NULL OR delivery_mode IN ('draft_only', 'auto_reply')", name="ck_ai_executions_delivery_mode"),
        CheckConstraint("reply_status IS NULL OR reply_status IN ('processing', 'draft_ready', 'sent', 'escalated', 'failed')", name="ck_ai_executions_reply_status"),
        UniqueConstraint("organization_id", "id", name="uq_ai_executions_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ai_executions_org_requester",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_ai_executions_org_conversation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_message_id"],
            ["messages.organization_id", "messages.id"],
            name="fk_ai_executions_org_source_message",
            ondelete="CASCADE",
        ),
        UniqueConstraint("organization_id", "source_message_id", name="uq_ai_executions_widget_source"),
        Index("ix_ai_executions_queue", "organization_id", "status", "next_attempt_at", "created_at"),
        Index("ix_ai_executions_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_mode: Mapped[str | None] = mapped_column(String(20))
    reply_status: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    # The prompt is private execution input and is never serialized by an API schema.
    question: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    # Optional, encrypted verified integration context. Never included in API output.
    integration_context_encrypted: Mapped[str | None] = mapped_column(Text)
    draft: Mapped[str | None] = mapped_column(Text)
    recommendation_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    safe_summary: Mapped[str | None] = mapped_column(String(500))
    citations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    tool_outcomes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    usage: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(120))
    error_code: Mapped[str | None] = mapped_column(String(80))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
