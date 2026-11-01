"""Add merchant recommendation policy and deduplicated analytics events."""

import sqlalchemy as sa
from alembic import op

revision = "0028_recommendation_settings_analytics"
down_revision = "0027_conversation_shopping_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Alembic's default ledger column is VARCHAR(32), but this revision ID is
    # 38 characters. Expand it inside the migration transaction before Alembic
    # writes the new revision into the ledger.
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)")
    op.create_table(
        "recommendation_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mode", sa.String(16), nullable=False, server_default="automatic"),
        sa.Column("max_products", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("in_stock_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("excluded_product_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("excluded_collection_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("comparison_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("upselling_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("cross_selling_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("ranking_preferences", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("human_handoff_preferences", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("mode IN ('automatic', 'explicit')", name="ck_recommendation_settings_mode"),
        sa.CheckConstraint("max_products BETWEEN 1 AND 5", name="ck_recommendation_settings_max_products"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", name="uq_recommendation_settings_organization"),
        sa.UniqueConstraint("organization_id", "id", name="uq_recommendation_settings_org_id"),
    )
    op.create_table(
        "recommendation_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("query_category", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("event_type IN ('impression', 'product_click', 'comparison', 'add_to_cart', 'purchase', 'rejection', 'no_result', 'human_handoff')", name="ck_recommendation_events_type"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id", "conversation_id"], ["conversations.organization_id", "conversations.id"], ondelete="CASCADE", name="fk_recommendation_events_org_conversation"),
        sa.ForeignKeyConstraint(["organization_id", "message_id"], ["messages.organization_id", "messages.id"], ondelete="CASCADE", name="fk_recommendation_events_org_message"),
        sa.ForeignKeyConstraint(["organization_id", "product_id"], ["catalog_products.organization_id", "catalog_products.id"], ondelete="CASCADE", name="fk_recommendation_events_org_product"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "event_id", name="uq_recommendation_events_org_event"),
    )
    op.create_index("ix_recommendation_events_org_created_type", "recommendation_events", ["organization_id", "created_at", "event_type"])
    op.create_index("ix_recommendation_events_org_product_created", "recommendation_events", ["organization_id", "product_id", "created_at"])
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE recommendation_settings ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE recommendation_settings FORCE ROW LEVEL SECURITY")
        op.execute("CREATE POLICY recommendation_settings_tenant_policy ON recommendation_settings USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)")
        op.execute("ALTER TABLE recommendation_events ENABLE ROW LEVEL SECURITY")
        op.execute("ALTER TABLE recommendation_events FORCE ROW LEVEL SECURITY")
        op.execute("CREATE POLICY recommendation_events_tenant_policy ON recommendation_events USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid) WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)")


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM recommendation_events")).scalar_one()
    if count:
        raise RuntimeError("Cannot downgrade while recommendation analytics events exist; export them first.")
    op.drop_index("ix_recommendation_events_org_product_created", table_name="recommendation_events")
    op.drop_index("ix_recommendation_events_org_created_type", table_name="recommendation_events")
    op.drop_table("recommendation_events")
    op.drop_table("recommendation_settings")
