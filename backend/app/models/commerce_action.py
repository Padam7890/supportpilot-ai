import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class CommerceAction(TimestampMixin, UUIDPrimaryKey, Base):
    """Human-reviewed order action with separate approval and execution state."""

    __tablename__ = "commerce_actions"
    __table_args__ = (
        CheckConstraint("action_type IN ('refund', 'cancel')", name="ck_commerce_actions_type"),
        CheckConstraint("provider IN ('mock', 'shopify')", name="ck_commerce_actions_provider"),
        CheckConstraint("provider = 'mock' OR action_type = 'cancel'", name="ck_commerce_actions_provider_type"),
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')",
            name="ck_commerce_actions_approval_status",
        ),
        CheckConstraint(
            "execution_status IN ('not_started', 'queued', 'running', 'succeeded', 'failed')",
            name="ck_commerce_actions_execution_status",
        ),
        CheckConstraint(
            "(action_type = 'refund' AND refund_amount IS NOT NULL AND refund_amount > 0) "
            "OR (action_type = 'cancel' AND refund_amount IS NULL)",
            name="ck_commerce_actions_amount_matches_type",
        ),
        CheckConstraint(
            "(approval_status IN ('pending', 'rejected', 'expired', 'cancelled') AND execution_status = 'not_started') "
            "OR (approval_status = 'approved' AND execution_status IN ('queued', 'running', 'succeeded', 'failed'))",
            name="ck_commerce_actions_state_pair",
        ),
        CheckConstraint(
            "execution_attempt_count >= 0",
            name="ck_commerce_actions_attempt_count",
        ),
        CheckConstraint(
            "((approval_status IN ('approved', 'rejected') AND reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL) "
            "OR (approval_status NOT IN ('approved', 'rejected') AND reviewed_by_user_id IS NULL AND reviewed_at IS NULL))",
            name="ck_commerce_actions_review_metadata",
        ),
        CheckConstraint(
            "((approval_status = 'cancelled' AND cancelled_by_user_id IS NOT NULL AND cancelled_at IS NOT NULL) "
            "OR (approval_status <> 'cancelled' AND cancelled_by_user_id IS NULL AND cancelled_at IS NULL))",
            name="ck_commerce_actions_cancel_metadata",
        ),
        UniqueConstraint("organization_id", "id", name="uq_commerce_actions_org_id"),
        UniqueConstraint(
            "organization_id", "idempotency_key_hash", name="uq_commerce_actions_org_idempotency"
        ),
        ForeignKeyConstraint(
            ["organization_id", "ticket_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_commerce_actions_org_ticket",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_commerce_actions_org_requester",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reviewed_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_commerce_actions_org_reviewer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "cancelled_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_commerce_actions_org_canceller",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_commerce_actions_queue",
            "organization_id",
            "approval_status",
            "execution_status",
            "updated_at",
        ),
        Index(
            "ix_commerce_actions_org_created",
            "organization_id",
            "created_at",
            "id",
        ),
        Index(
            "uq_commerce_actions_pending_shopify_cancel_order",
            "organization_id",
            "shopify_order_id",
            unique=True,
            postgresql_where=text("provider = 'shopify' AND action_type = 'cancel' AND approval_status = 'pending'"),
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    action_type: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), default="mock", nullable=False)
    shopify_order_id: Mapped[str] = mapped_column(String(120), nullable=False)
    order_number: Mapped[str] = mapped_column(String(60), nullable=False)
    order_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    refund_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    cancel_refund: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_restock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancel_notify_customer: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cancellation_reason: Mapped[str] = mapped_column(String(20), default="CUSTOMER", nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_status: Mapped[str] = mapped_column(String(20), default="not_started", nullable=False)
    execution_attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    execution_result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    execution_error_code: Mapped[str | None] = mapped_column(String(80))
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CommerceActionAudit(UUIDPrimaryKey, Base):
    __tablename__ = "commerce_action_audits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "commerce_action_id"],
            ["commerce_actions.organization_id", "commerce_actions.id"],
            name="fk_commerce_action_audits_org_action",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_commerce_action_audits_org_actor",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_commerce_action_audits_org_action_time",
            "organization_id",
            "commerce_action_id",
            "created_at",
            "id",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    commerce_action_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
