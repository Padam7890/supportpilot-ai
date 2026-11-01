import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
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


class RecommendationSettings(UUIDPrimaryKey, TimestampMixin, Base):
    """Validated merchant policy for the recommendation experience."""

    __tablename__ = "recommendation_settings"
    __table_args__ = (
        CheckConstraint("mode IN ('automatic', 'explicit')", name="ck_recommendation_settings_mode"),
        CheckConstraint("max_products BETWEEN 1 AND 5", name="ck_recommendation_settings_max_products"),
        UniqueConstraint("organization_id", name="uq_recommendation_settings_organization"),
        UniqueConstraint("organization_id", "id", name="uq_recommendation_settings_org_id"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), default="automatic", nullable=False)
    max_products: Mapped[int] = mapped_column(default=3, nullable=False)
    in_stock_only: Mapped[bool] = mapped_column(default=False, nullable=False)
    excluded_product_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    excluded_collection_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    comparison_enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    upselling_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    cross_selling_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    ranking_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    human_handoff_preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class RecommendationEvent(UUIDPrimaryKey, Base):
    """Deduplicated, tenant-scoped product recommendation telemetry."""

    __tablename__ = "recommendation_events"
    __table_args__ = (
        CheckConstraint("event_type IN ('impression', 'product_click', 'comparison', 'add_to_cart', 'purchase', 'rejection', 'no_result', 'human_handoff')", name="ck_recommendation_events_type"),
        UniqueConstraint("organization_id", "event_id", name="uq_recommendation_events_org_event"),
        ForeignKeyConstraint(["organization_id", "conversation_id"], ["conversations.organization_id", "conversations.id"], name="fk_recommendation_events_org_conversation", ondelete="CASCADE"),
        ForeignKeyConstraint(["organization_id", "message_id"], ["messages.organization_id", "messages.id"], name="fk_recommendation_events_org_message", ondelete="CASCADE"),
        ForeignKeyConstraint(["organization_id", "product_id"], ["catalog_products.organization_id", "catalog_products.id"], name="fk_recommendation_events_org_product", ondelete="CASCADE"),
        Index("ix_recommendation_events_org_created_type", "organization_id", "created_at", "event_type"),
        Index("ix_recommendation_events_org_product_created", "organization_id", "product_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    variant_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    # Optional safe, coarse query descriptor (category only); no raw customer text or identity.
    query_category: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
