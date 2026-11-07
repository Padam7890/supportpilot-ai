import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
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
        UniqueConstraint(
            "organization_id",
            "id",
            "integration_connection_id",
            name="uq_conversations_org_id_connection",
        ),
        UniqueConstraint(
            "organization_id",
            "integration_connection_id",
            "external_conversation_id",
            name="uq_conversations_provider_external",
        ),
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
        ForeignKeyConstraint(
            ["organization_id", "ai_agent_id"],
            ["ai_agents.organization_id", "ai_agents.id"],
            name="fk_conversations_org_agent",
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
    ai_agent_override: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    integration_connection_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    ai_agent_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    external_conversation_id: Mapped[str | None] = mapped_column(String(512))
    # Compact, non-PII shopping preferences for this conversation only.
    shopping_state: Mapped[dict | None] = mapped_column(JSON)
    shopping_state_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shopping_state_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    ticket = relationship("Ticket", back_populates="conversations")
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        foreign_keys="Message.conversation_id,Message.organization_id",
    )

    @property
    def shopping_context(self) -> dict | None:
        """Expose only unexpired, compact shopping context to authenticated teammates."""
        if not self.shopping_state or self.shopping_state_expires_at is None:
            return None
        expires = self.shopping_state_expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= datetime.now(UTC):
            return None
        return self.shopping_state
