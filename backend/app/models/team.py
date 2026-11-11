import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class Team(TimestampMixin, UUIDPrimaryKey, Base):
    """A tenant-owned support team used for ticket routing."""

    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_teams_org_id"),
        UniqueConstraint("organization_id", "name", name="uq_teams_org_name"),
        Index("ix_teams_org_active_name", "organization_id", "is_active", "name"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class TeamMember(Base):
    """Tenant-safe membership linking an active workspace member to a team."""

    __tablename__ = "team_members"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["teams.organization_id", "teams.id"],
            name="fk_team_members_org_team",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_team_members_org_user",
            ondelete="CASCADE",
        ),
        Index("ix_team_members_org_user", "organization_id", "user_id", "team_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    team_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)


class TeamAudit(UUIDPrimaryKey, Base):
    """Audit record for team creation, edits, activation, and membership changes."""

    __tablename__ = "team_audits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "team_id"],
            ["teams.organization_id", "teams.id"],
            name="fk_team_audits_org_team",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_team_audits_org_actor",
            ondelete="RESTRICT",
        ),
        Index("ix_team_audits_org_team_created", "organization_id", "team_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
