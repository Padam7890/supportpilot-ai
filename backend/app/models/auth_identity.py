import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class AuthIdentity(UUIDPrimaryKey, TimestampMixin, Base):
    """Global sign-in identity; workspace data remains on tenant-scoped User rows."""

    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("email_normalized", name="uq_auth_identities_email_normalized"),
    )

    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    password_reset_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AuthIdentityMembership(UUIDPrimaryKey, Base):
    """Narrow auth directory linking a global identity to one tenant membership."""

    __tablename__ = "auth_identity_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_auth_identity_membership_user"),
        UniqueConstraint("identity_id", "organization_id", name="uq_auth_identity_membership_org"),
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_auth_identity_memberships_org_user",
            ondelete="CASCADE",
        ),
        Index("ix_auth_identity_memberships_identity", "identity_id", "organization_id"),
    )

    identity_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_identities.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)


class AuthChallenge(UUIDPrimaryKey, Base):
    """Short-lived, one-time pre-auth challenge; only token and OTP digests are stored."""

    __tablename__ = "auth_challenges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_auth_challenges_org_user",
            ondelete="CASCADE",
        ),
        UniqueConstraint("token_hash", name="uq_auth_challenges_token_hash"),
        CheckConstraint(
            "purpose IN ('login', 'registration', 'password_reset')",
            name="ck_auth_challenges_purpose",
        ),
        CheckConstraint("attempt_count BETWEEN 0 AND 5", name="ck_auth_challenges_attempt_count"),
        CheckConstraint("send_count BETWEEN 0 AND 3", name="ck_auth_challenges_send_count"),
        Index(
            "ix_auth_challenges_identity_purpose_created", "identity_id", "purpose", "created_at"
        ),
    )

    identity_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("auth_identities.id", ondelete="CASCADE"), nullable=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(24), nullable=False)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    code_digest: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    send_count: Mapped[int] = mapped_column(default=0, nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
