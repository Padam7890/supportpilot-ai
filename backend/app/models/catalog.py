"""Tenant-scoped normalized commerce catalog and synchronization state."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKey


class CatalogProduct(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "catalog_products"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'draft', 'archived', 'unknown')",
            name="ck_catalog_products_status",
        ),
        UniqueConstraint("organization_id", "id", name="uq_catalog_products_org_id"),
        UniqueConstraint(
            "organization_id", "connection_id", "external_product_id",
            name="uq_catalog_products_external",
        ),
        ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_catalog_products_org_connection",
            ondelete="CASCADE",
        ),
        Index("ix_catalog_products_org_status_title", "organization_id", "status", "title"),
        Index("ix_catalog_products_org_synced", "organization_id", "synced_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    external_product_id: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(255))
    images: Mapped[list[dict[str, str | None]]] = mapped_column(JSON, default=list, nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(2048))
    status: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    specifications: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_sync_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    variants: Mapped[list["CatalogVariant"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class CatalogVariant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "catalog_variants"
    __table_args__ = (
        CheckConstraint(
            "availability IN ('available', 'unavailable', 'unknown')",
            name="ck_catalog_variants_availability",
        ),
        CheckConstraint("price >= 0", name="ck_catalog_variants_price_nonnegative"),
        CheckConstraint(
            "compare_at_price IS NULL OR compare_at_price >= 0",
            name="ck_catalog_variants_compare_price_nonnegative",
        ),
        UniqueConstraint(
            "organization_id", "connection_id", "external_variant_id",
            name="uq_catalog_variants_external",
        ),
        ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["catalog_products.organization_id", "catalog_products.id"],
            name="fk_catalog_variants_org_product",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_catalog_variants_org_connection",
            ondelete="CASCADE",
        ),
        Index("ix_catalog_variants_org_product", "organization_id", "product_id"),
        Index("ix_catalog_variants_org_availability", "organization_id", "availability"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    external_variant_id: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str | None] = mapped_column(String(255))
    attributes: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    compare_at_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    availability: Mapped[str] = mapped_column(String(16), default="unknown", nullable=False)
    inventory_quantity: Mapped[int | None] = mapped_column()
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    product: Mapped[CatalogProduct] = relationship(back_populates="variants")


class CatalogSyncJob(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "catalog_sync_jobs"
    __table_args__ = (
        CheckConstraint("mode IN ('full', 'incremental', 'reconcile')", name="ck_catalog_sync_mode"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_catalog_sync_status",
        ),
        CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_catalog_sync_attempts"),
        CheckConstraint("max_attempts > 0", name="ck_catalog_sync_max_attempts"),
        ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_catalog_sync_jobs_org_connection",
            ondelete="CASCADE",
        ),
        Index("ix_catalog_sync_jobs_queue", "organization_id", "status", "next_attempt_at", "created_at"),
        Index("ix_catalog_sync_jobs_org_connection", "organization_id", "connection_id", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    cursor: Mapped[str | None] = mapped_column(String(2048))
    updated_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sync_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=5, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    records_seen: Mapped[int] = mapped_column(default=0, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CatalogWebhookEvent(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "catalog_webhook_events"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_catalog_webhook_events_status",
        ),
        CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_catalog_webhook_attempts"),
        UniqueConstraint(
            "organization_id", "connection_id", "provider_id", "external_event_id",
            name="uq_catalog_webhook_events_dedupe",
        ),
        ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_catalog_webhook_events_org_connection",
            ondelete="CASCADE",
        ),
        Index("ix_catalog_webhook_events_queue", "organization_id", "status", "next_attempt_at", "created_at"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(48), nullable=False)
    external_event_id: Mapped[str] = mapped_column(String(512), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    external_product_id: Mapped[str] = mapped_column(String(512), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=5, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
