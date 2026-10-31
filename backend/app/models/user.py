import uuid

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_users_org_email"),
        UniqueConstraint("organization_id", "id", name="uq_users_org_id"),
        Index("ix_users_org_id_id", "organization_id", "id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="agent", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    organization = relationship("Organization", back_populates="users")
    assigned_tickets = relationship(
        "Ticket", back_populates="assignee", foreign_keys="Ticket.assignee_id"
    )
