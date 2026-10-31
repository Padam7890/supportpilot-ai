from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class PlatformOwner(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "platform_owners"
    __table_args__ = (UniqueConstraint("email", name="uq_platform_owners_email"),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    refresh_sessions = relationship(
        "PlatformRefreshSession", back_populates="platform_owner", cascade="all, delete-orphan"
    )
