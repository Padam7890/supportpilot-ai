import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class TeamInvitation(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "team_invitations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_team_invitations_org_id"),
        UniqueConstraint("token_hash", name="uq_team_invitations_token_hash"),
        ForeignKeyConstraint(
            ["organization_id", "invited_by_id"],
            ["users.organization_id", "users.id"],
            name="fk_team_invitations_org_inviter",
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    invited_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
