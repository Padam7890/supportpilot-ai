from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class PlatformOwner(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "platform_owners"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    refresh_sessions = relationship(
        "PlatformRefreshSession", back_populates="platform_owner", cascade="all, delete-orphan"
    )
