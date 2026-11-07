import uuid

from sqlalchemy import Boolean, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class SavedReply(TimestampMixin, UUIDPrimaryKey, Base):
    """Reusable, tenant-owned reply text for support agents."""

    __tablename__ = "saved_replies"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_saved_replies_org_id"),
        UniqueConstraint("organization_id", "shortcut", name="uq_saved_replies_org_shortcut"),
        ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_saved_replies_org_creator",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "updated_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_saved_replies_org_updater",
            ondelete="RESTRICT",
        ),
        Index("ix_saved_replies_org_active_title", "organization_id", "is_active", "title"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    shortcut: Mapped[str] = mapped_column(String(40), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    updated_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
