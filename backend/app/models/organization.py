import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class Organization(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected')",
            name="ck_organizations_approval_status",
        ),
        Index("ix_organizations_approval_created", "approval_status", "created_at"),
    )

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    approval_status: Mapped[str] = mapped_column(String(20), default="approved", nullable=False)
    reviewed_by_platform_owner_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "platform_owners.id",
            ondelete="SET NULL",
            name="fk_organizations_reviewed_by_platform_owner",
        )
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_sla_minutes: Mapped[dict] = mapped_column(
        JSONB,
        default=lambda: {"low": 1440, "normal": 480, "high": 120, "urgent": 30},
        server_default=text(
            '\'{"low"\\:1440,"normal"\\:480,"high"\\:120,"urgent"\\:30}\'::jsonb'
        ),
        nullable=False,
    )

    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    customers = relationship(
        "Customer", back_populates="organization", cascade="all, delete-orphan"
    )
    tickets = relationship("Ticket", back_populates="organization", cascade="all, delete-orphan")
