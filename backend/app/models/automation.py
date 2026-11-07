import uuid
from datetime import UTC, datetime, timedelta
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
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey

APPROVAL_REVIEW_WINDOW = timedelta(days=7)


class AutomationWorkflow(UUIDPrimaryKey, TimestampMixin, Base):
    """Tenant-owned editable workflow and published-version pointer."""

    __tablename__ = "automation_workflows"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_automation_workflows_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_automation_workflows_org_creator",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('draft', 'active', 'paused')", name="ck_automation_workflows_status"),
        CheckConstraint("published_version IS NULL OR published_version > 0", name="ck_automation_workflows_version"),
        CheckConstraint("draft_version > 0", name="ck_automation_workflows_draft_version"),
        Index("ix_automation_workflows_org_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False)
    draft_definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    draft_canvas_layout: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    published_version: Mapped[int | None] = mapped_column(Integer)
    draft_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))


class AutomationWorkflowVersion(UUIDPrimaryKey, Base):
    """Immutable published workflow definition used by queued executions."""

    __tablename__ = "automation_workflow_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_automation_workflow_versions_org_id"),
        UniqueConstraint("organization_id", "workflow_id", "version", name="uq_automation_workflow_versions_revision"),
        ForeignKeyConstraint(
            ["organization_id", "workflow_id"],
            ["automation_workflows.organization_id", "automation_workflows.id"],
            name="fk_automation_workflow_versions_org_workflow",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "published_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_automation_workflow_versions_org_publisher",
            ondelete="RESTRICT",
        ),
        CheckConstraint("version > 0", name="ck_automation_workflow_versions_version"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    canvas_layout: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    published_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


class AutomationExecutionEffect(UUIDPrimaryKey, Base):
    """Recorded idempotency key for a logical side effect within one execution (replay-safe)."""

    __tablename__ = "automation_execution_effects"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "execution_id",
            "effect_key",
            name="uq_automation_execution_effects_org_exec_key",
        ),
        ForeignKeyConstraint(
            ["organization_id", "execution_id"],
            ["automation_executions.organization_id", "automation_executions.id"],
            name="fk_automation_execution_effects_org_execution",
            ondelete="CASCADE",
        ),
        Index("ix_automation_execution_effects_org_exec", "organization_id", "execution_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    effect_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class AutomationExecution(UUIDPrimaryKey, TimestampMixin, Base):
    """Durable, idempotent execution of one published workflow for one event."""

    __tablename__ = "automation_executions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_automation_executions_org_id"),
        UniqueConstraint("organization_id", "workflow_id", "event_key", name="uq_automation_executions_event"),
        ForeignKeyConstraint(
            ["organization_id", "workflow_id"],
            ["automation_workflows.organization_id", "automation_workflows.id"],
            name="fk_automation_executions_org_workflow",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_automation_executions_org_conversation",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "ticket_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_automation_executions_org_ticket",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_message_id"],
            ["messages.organization_id", "messages.id"],
            name="fk_automation_executions_org_message",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "version_id"],
            ["automation_workflow_versions.organization_id", "automation_workflow_versions.id"],
            name="fk_automation_executions_org_version",
            ondelete="RESTRICT",
        ),
        CheckConstraint("status IN ('queued', 'running', 'waiting_approval', 'succeeded', 'failed', 'rejected', 'expired')", name="ck_automation_executions_status"),
        CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_automation_executions_attempts"),
        Index("ix_automation_executions_queue", "organization_id", "status", "next_attempt_at", "created_at"),
        Index("ix_automation_executions_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    source_message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_key: Mapped[str] = mapped_column(String(80), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64))
    lease_token: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AutomationExecutionApproval(UUIDPrimaryKey, Base):
    """Tenant-scoped human decision point within a durable workflow execution."""

    __tablename__ = "automation_execution_approvals"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "execution_id", "action_index",
            name="uq_automation_execution_approvals_org_execution_step",
        ),
        ForeignKeyConstraint(
            ["organization_id", "execution_id"],
            ["automation_executions.organization_id", "automation_executions.id"],
            name="fk_automation_execution_approvals_org_execution",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reviewed_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_automation_execution_approvals_org_reviewer",
            ondelete="RESTRICT",
        ),
        CheckConstraint("action_index >= 0", name="ck_automation_execution_approvals_action_index"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'expired')", name="ck_automation_execution_approvals_status"),
        Index("ix_automation_execution_approvals_org_status", "organization_id", "status", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    execution_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action_index: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC) + APPROVAL_REVIEW_WINDOW,
        nullable=False,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

