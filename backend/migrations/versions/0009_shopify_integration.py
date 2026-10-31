"""Add tenant-isolated Shopify OAuth connections and access audit."""

import sqlalchemy as sa
from alembic import op

revision = "0009_shopify_integration"
down_revision = "0008_knowledge_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopify_installations",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("shop_domain", sa.String(255), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=True),
        sa.Column("refresh_token_encrypted", sa.Text(), nullable=True),
        sa.Column("access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_scopes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("connected_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "connected_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_shopify_installations_org_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("organization_id"),
        sa.UniqueConstraint("organization_id", name="uq_shopify_installations_org"),
    )
    op.create_index(
        "uq_shopify_installations_active_shop",
        "shopify_installations",
        ["shop_domain"],
        unique=True,
        postgresql_where=sa.text("disconnected_at IS NULL"),
    )

    op.create_table(
        "shopify_oauth_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("shop_domain", sa.String(255), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_shopify_oauth_states_org_user",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash", name="uq_shopify_oauth_states_hash"),
    )
    op.create_index(
        "ix_shopify_oauth_states_org_expires",
        "shopify_oauth_states",
        ["organization_id", "expires_at"],
    )

    op.create_table(
        "shopify_access_audit",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("resource_type", sa.String(30), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("query_fingerprint", sa.String(64), nullable=False),
        sa.Column("details", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_shopify_access_audit_org_user",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_shopify_access_audit_org_time",
        "shopify_access_audit",
        ["organization_id", "created_at"],
    )

    for table in ("shopify_installations", "shopify_oauth_states", "shopify_access_audit"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
            USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
        )


def downgrade() -> None:
    for table in ("shopify_access_audit", "shopify_oauth_states", "shopify_installations"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.drop_table(table)
