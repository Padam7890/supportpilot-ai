import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class ShopifyInstallation(TimestampMixin, Base):
    __tablename__ = "shopify_installations"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_shopify_installations_org"),
        Index(
            "uq_shopify_installations_active_shop",
            "shop_domain",
            unique=True,
            postgresql_where=text("disconnected_at IS NULL"),
        ),
        ForeignKeyConstraint(
            ["organization_id", "connected_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_shopify_installations_org_user",
            ondelete="RESTRICT",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True
    )
    shop_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="oauth", server_default="oauth")
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refresh_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    granted_scopes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    connected_by_user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ShopifyOAuthState(UUIDPrimaryKey, Base):
    __tablename__ = "shopify_oauth_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_shopify_oauth_states_org_user",
            ondelete="CASCADE",
        ),
        UniqueConstraint("state_hash", name="uq_shopify_oauth_states_hash"),
        Index("ix_shopify_oauth_states_org_expires", "organization_id", "expires_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    shop_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class ShopifyAccessAudit(UUIDPrimaryKey, Base):
    __tablename__ = "shopify_access_audit"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_shopify_access_audit_org_user",
            ondelete="RESTRICT",
        ),
        Index("ix_shopify_access_audit_org_time", "organization_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)
    result_count: Mapped[int] = mapped_column(nullable=False)
    query_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
