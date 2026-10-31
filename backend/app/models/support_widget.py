import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
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


class SupportWidget(TimestampMixin, UUIDPrimaryKey, Base):
    __tablename__ = "support_widgets"
    __table_args__ = (
        CheckConstraint("ai_reply_mode IN ('draft_only', 'auto_reply')", name="ck_support_widgets_ai_reply_mode"),
        UniqueConstraint("organization_id", name="uq_support_widgets_organization"),
        UniqueConstraint("public_id", name="uq_support_widgets_public_id"),
        UniqueConstraint("organization_id", "id", name="uq_support_widgets_org_id"),
        Index("ix_support_widgets_org_enabled", "organization_id", "enabled"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    public_id: Mapped[str] = mapped_column(String(48), nullable=False)
    allowed_origins: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    collect_contact: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_reply_mode: Mapped[str] = mapped_column(String(20), default="draft_only", nullable=False)


class WidgetSubmission(UUIDPrimaryKey, Base):
    """First-message idempotency receipt; committed with ticket and conversation."""

    __tablename__ = "widget_submissions"
    __table_args__ = (
        UniqueConstraint(
            "widget_id", "idempotency_key_hash", name="uq_widget_submissions_widget_key"
        ),
        ForeignKeyConstraint(
            ["organization_id", "widget_id"],
            ["support_widgets.organization_id", "support_widgets.id"],
            name="fk_widget_submissions_org_widget",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "ticket_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_widget_submissions_org_ticket",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_widget_submissions_org_conversation",
            ondelete="CASCADE",
        ),
        Index("ix_widget_submissions_org_created", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    widget_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    visitor_token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    contact_consent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contact_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class WidgetOrderVerification(UUIDPrimaryKey, Base):
    """Short-lived, tenant-scoped OTP state for a verified Shopify order lookup."""

    __tablename__ = "widget_order_verifications"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'verified', 'expired', 'locked')", name="ck_widget_order_verification_status"),
        CheckConstraint("attempt_count BETWEEN 0 AND 5", name="ck_widget_order_verification_attempts"),
        ForeignKeyConstraint(
            ["organization_id", "widget_id"],
            ["support_widgets.organization_id", "support_widgets.id"],
            name="fk_widget_order_verifications_org_widget",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_widget_order_verifications_org_conversation",
            ondelete="CASCADE",
        ),
        Index("ix_widget_order_verifications_lookup", "organization_id", "conversation_id", "status", "expires_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    widget_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    order_number: Mapped[str] = mapped_column(String(60), nullable=False)
    shopify_order_id: Mapped[str] = mapped_column(String(180), nullable=False)
    customer_email_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    code_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
