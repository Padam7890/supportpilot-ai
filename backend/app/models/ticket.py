import uuid

from sqlalchemy import (
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


class Ticket(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_org_status_created", "organization_id", "status", "created_at"),
        Index("ix_tickets_org_customer", "organization_id", "customer_id"),
        UniqueConstraint("organization_id", "id", name="uq_tickets_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "customer_id"],
            ["customers.organization_id", "customers.id"],
            name="fk_tickets_org_customer",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "assignee_id"],
            ["users.organization_id", "users.id"],
            name="fk_tickets_org_assignee",
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    subject: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)

    organization = relationship("Organization", back_populates="tickets")
    customer = relationship("Customer", back_populates="tickets")
    assignee = relationship("User", back_populates="assigned_tickets", foreign_keys=[assignee_id])
    conversations = relationship(
        "Conversation", back_populates="ticket", cascade="all, delete-orphan"
    )
