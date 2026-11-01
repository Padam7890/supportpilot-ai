import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class Conversation(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("ai_mode IN ('ai', 'human')", name="ck_conversations_ai_mode"),
        Index("ix_conversations_org_ticket", "organization_id", "ticket_id"),
        Index(
            "ix_conversations_org_connection_external",
            "organization_id",
            "integration_connection_id",
            "external_conversation_id",
        ),
        UniqueConstraint("organization_id", "id", name="uq_conversations_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "ticket_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_conversations_org_ticket",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "integration_connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_conversations_org_integration_connection",
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    channel: Mapped[str] = mapped_column(String(30), default="web", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    ai_mode: Mapped[str] = mapped_column(
        String(12), default="human", server_default="human", nullable=False
    )
    integration_connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    external_conversation_id: Mapped[str | None] = mapped_column(String(512))

    ticket = relationship("Ticket", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
