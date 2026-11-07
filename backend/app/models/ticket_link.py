import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import UUIDPrimaryKey


class TicketLink(UUIDPrimaryKey, Base):
    """A tenant-scoped, non-destructive relationship between two tickets."""

    __tablename__ = "ticket_links"
    __table_args__ = (
        CheckConstraint("ticket_low_id < ticket_high_id", name="ck_ticket_links_canonical_order"),
        UniqueConstraint(
            "organization_id",
            "ticket_low_id",
            "ticket_high_id",
            name="uq_ticket_links_org_pair",
        ),
        ForeignKeyConstraint(
            ["organization_id", "ticket_low_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_ticket_links_org_low_ticket",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "ticket_high_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_ticket_links_org_high_ticket",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ticket_links_org_creator",
            ondelete="RESTRICT",
        ),
        Index("ix_ticket_links_org_low_created", "organization_id", "ticket_low_id", "created_at"),
        Index("ix_ticket_links_org_high_created", "organization_id", "ticket_high_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    ticket_low_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ticket_high_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
