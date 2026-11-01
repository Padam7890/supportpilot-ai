"""Add tenant-scoped commerce catalog, sync jobs, and webhook inbox."""

import sqlalchemy as sa
from alembic import op

revision = "0025_commerce_catalog"
down_revision = "0024_normalized_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_products",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("external_product_id", sa.String(512), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("category", sa.String(255), nullable=True),
        sa.Column("images", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("canonical_url", sa.String(2048), nullable=True),
        sa.Column("status", sa.String(16), server_default="unknown", nullable=False),
        sa.Column("specifications", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_sync_id", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'draft', 'archived', 'unknown')", name="ck_catalog_products_status"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_catalog_products_org_connection", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_catalog_products_org_id"),
        sa.UniqueConstraint(
            "organization_id", "connection_id", "external_product_id",
            name="uq_catalog_products_external",
        ),
    )
    op.create_index("ix_catalog_products_org_status_title", "catalog_products", ["organization_id", "status", "title"])
    op.create_index("ix_catalog_products_org_synced", "catalog_products", ["organization_id", "synced_at"])

    op.create_table(
        "catalog_variants",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("external_variant_id", sa.String(512), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("sku", sa.String(255), nullable=True),
        sa.Column("attributes", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("price", sa.Numeric(20, 4), nullable=False),
        sa.Column("compare_at_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("availability", sa.String(16), server_default="unknown", nullable=False),
        sa.Column("inventory_quantity", sa.Integer(), nullable=True),
        sa.Column("provider_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("availability IN ('available', 'unavailable', 'unknown')", name="ck_catalog_variants_availability"),
        sa.CheckConstraint("price >= 0", name="ck_catalog_variants_price_nonnegative"),
        sa.CheckConstraint("compare_at_price IS NULL OR compare_at_price >= 0", name="ck_catalog_variants_compare_price_nonnegative"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "product_id"], ["catalog_products.organization_id", "catalog_products.id"],
            name="fk_catalog_variants_org_product", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_catalog_variants_org_connection", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "connection_id", "external_variant_id", name="uq_catalog_variants_external"),
    )
    op.create_index("ix_catalog_variants_org_product", "catalog_variants", ["organization_id", "product_id"])
    op.create_index("ix_catalog_variants_org_availability", "catalog_variants", ["organization_id", "availability"])

    op.create_table(
        "catalog_sync_jobs",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("cursor", sa.String(2048), nullable=True),
        sa.Column("updated_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("mode IN ('full', 'incremental', 'reconcile')", name="ck_catalog_sync_mode"),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')", name="ck_catalog_sync_status"),
        sa.CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_catalog_sync_attempts"),
        sa.CheckConstraint("max_attempts > 0", name="ck_catalog_sync_max_attempts"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_catalog_sync_jobs_org_connection", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_catalog_sync_jobs_queue", "catalog_sync_jobs", ["organization_id", "status", "next_attempt_at", "created_at"])
    op.create_index("ix_catalog_sync_jobs_org_connection", "catalog_sync_jobs", ["organization_id", "connection_id", "created_at"])

    op.create_table(
        "catalog_webhook_events",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(48), nullable=False),
        sa.Column("external_event_id", sa.String(512), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("external_product_id", sa.String(512), nullable=False),
        sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("status", sa.String(16), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_catalog_webhook_events_status"),
        sa.CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_catalog_webhook_attempts"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_catalog_webhook_events_org_connection", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "connection_id", "provider_id", "external_event_id", name="uq_catalog_webhook_events_dedupe"),
    )
    op.create_index("ix_catalog_webhook_events_queue", "catalog_webhook_events", ["organization_id", "status", "next_attempt_at", "created_at"])

    tenant_predicate = "organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    for table in ("catalog_products", "catalog_variants", "catalog_sync_jobs", "catalog_webhook_events"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
            USING ({tenant_predicate}) WITH CHECK ({tenant_predicate})'''
        )


def downgrade() -> None:
    for table in ("catalog_webhook_events", "catalog_sync_jobs", "catalog_variants", "catalog_products"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    for index, table in (
        ("ix_catalog_webhook_events_queue", "catalog_webhook_events"),
        ("ix_catalog_sync_jobs_org_connection", "catalog_sync_jobs"),
        ("ix_catalog_sync_jobs_queue", "catalog_sync_jobs"),
        ("ix_catalog_variants_org_availability", "catalog_variants"),
        ("ix_catalog_variants_org_product", "catalog_variants"),
        ("ix_catalog_products_org_synced", "catalog_products"),
        ("ix_catalog_products_org_status_title", "catalog_products"),
    ):
        op.drop_index(index, table_name=table)
    for table in ("catalog_webhook_events", "catalog_sync_jobs", "catalog_variants", "catalog_products"):
        op.drop_table(table)
