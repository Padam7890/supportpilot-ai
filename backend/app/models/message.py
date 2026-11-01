import uuid

from sqlalchemy import (
    JSON,
    CheckConstraint,
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


class Message(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "delivery_status IS NULL OR delivery_status IN "
            "('received', 'accepted', 'sent', 'delivered', 'failed', 'unknown')",
            name="ck_messages_delivery_status",
        ),
        Index(
            "ix_messages_org_conversation_created",
            "organization_id",
            "conversation_id",
            "created_at",
        ),
        UniqueConstraint("organization_id", "id", name="uq_messages_org_id"),
        UniqueConstraint(
            "organization_id",
            "conversation_id",
            "external_message_id",
            name="uq_messages_provider_external_id",
        ),
        UniqueConstraint(
            "organization_id",
            "conversation_id",
            "widget_idempotency_hash",
            name="uq_messages_widget_idempotency",
        ),
        ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_messages_org_conversation",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "sender_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_messages_org_sender",
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    sender_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # customer, agent, assistant, system, internal_note
    sender_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(String(30), default="text", nullable=False)
    widget_idempotency_hash: Mapped[str | None] = mapped_column(String(64))
    external_message_id: Mapped[str | None] = mapped_column(String(512))
    delivery_status: Mapped[str | None] = mapped_column(String(24))
    provider_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
