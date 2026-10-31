import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class PlatformRefreshSession(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "platform_refresh_sessions"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_platform_refresh_token_hash"),)

    platform_owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("platform_owners.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    platform_owner = relationship("PlatformOwner", back_populates="refresh_sessions")
