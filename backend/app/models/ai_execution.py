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
        CheckConstraint(
            "manual_retry_count >= 0 AND manual_retry_count <= 3",
            name="ck_ai_executions_manual_retry_count",
        ),
        CheckConstraint(
            "(manual_retry_count = 0 AND last_manual_retry_by_user_id IS NULL AND last_manual_retry_at IS NULL) "
            "OR (manual_retry_count > 0 AND last_manual_retry_by_user_id IS NOT NULL AND last_manual_retry_at IS NOT NULL)",
            name="ck_ai_executions_manual_retry_metadata",
        ),
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
            ["organization_id", "last_manual_retry_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ai_executions_org_manual_retry_actor",
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
        ForeignKeyConstraint(
            ["organization_id", "ai_agent_id"],
            ["ai_agents.organization_id", "ai_agents.id"],
            name="fk_ai_executions_org_agent",
            ondelete="RESTRICT",
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
    ai_agent_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ai_agent_config_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    delivery_mode: Mapped[str | None] = mapped_column(String(20))
    reply_status: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    # The prompt is private execution input and is never serialized by an API schema.
    question: Mapped[str] = mapped_column(Text, nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    # Bounded authenticated Playground context; separate from customer conversations.
    playground_history: Mapped[list[dict[str, str]] | None] = mapped_column(JSON)
    # Bot instructions are captured with the version at enqueue time so a later
    # configuration edit cannot silently change an already queued execution.
    ai_agent_instructions_snapshot: Mapped[str | None] = mapped_column(Text)
    # Closed recommendation-tool allowlist captured when the job is enqueued.
    ai_agent_tools_snapshot: Mapped[list[str] | None] = mapped_column(JSON)
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
    manual_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_manual_retry_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    last_manual_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
