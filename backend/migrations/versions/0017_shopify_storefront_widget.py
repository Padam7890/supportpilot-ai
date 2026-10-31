"""Add tenant-managed Shopify storefront chat widgets and inbound records."""

import sqlalchemy as sa
from alembic import op

revision = "0017_shopify_storefront_widget"
down_revision = "0016_shopify_cancel_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("source", sa.String(32), server_default="manual", nullable=False))
    op.create_check_constraint(
        "ck_tickets_source", "tickets", "source IN ('manual', 'shopify_widget')"
    )
    op.add_column("messages", sa.Column("widget_idempotency_hash", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_messages_widget_idempotency",
        "messages",
        ["organization_id", "conversation_id", "widget_idempotency_hash"],
    )

    op.create_table(
        "support_widgets",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.String(48), nullable=False),
        sa.Column("allowed_origins", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("collect_contact", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", name="uq_support_widgets_organization"),
        sa.UniqueConstraint("public_id", name="uq_support_widgets_public_id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_support_widgets_org_id"),
    )
    op.create_index("ix_support_widgets_org_enabled", "support_widgets", ["organization_id", "enabled"])

    op.create_table(
        "widget_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("widget_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("visitor_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contact_consent", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("contact_consent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "widget_id"],
            ["support_widgets.organization_id", "support_widgets.id"],
            name="fk_widget_submissions_org_widget",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "ticket_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_widget_submissions_org_ticket",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_widget_submissions_org_conversation",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("widget_id", "idempotency_key_hash", name="uq_widget_submissions_widget_key"),
    )
    op.create_index("ix_widget_submissions_org_created", "widget_submissions", ["organization_id", "created_at"])

    # Public lookup is limited to enabled widgets. Mutations remain tenant-scoped.
    op.execute("ALTER TABLE support_widgets ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE support_widgets FORCE ROW LEVEL SECURITY")
    tenant = "organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    op.execute(
        f"""CREATE POLICY support_widgets_public_read ON support_widgets FOR SELECT
        USING (enabled = true OR {tenant})"""
    )
    op.execute(f"CREATE POLICY support_widgets_tenant_insert ON support_widgets FOR INSERT WITH CHECK ({tenant})")
    op.execute(
        f"CREATE POLICY support_widgets_tenant_update ON support_widgets FOR UPDATE USING ({tenant}) WITH CHECK ({tenant})"
    )
    op.execute(f"CREATE POLICY support_widgets_tenant_delete ON support_widgets FOR DELETE USING ({tenant})")
    for table in ("widget_submissions",):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
            USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
        )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON widget_submissions")
    for policy in (
        "support_widgets_public_read",
        "support_widgets_tenant_insert",
        "support_widgets_tenant_update",
        "support_widgets_tenant_delete",
    ):
        op.execute(f"DROP POLICY IF EXISTS {policy} ON support_widgets")
    op.drop_index("ix_widget_submissions_org_created", table_name="widget_submissions")
    op.drop_table("widget_submissions")
    op.drop_index("ix_support_widgets_org_enabled", table_name="support_widgets")
    op.drop_table("support_widgets")
    op.drop_constraint("uq_messages_widget_idempotency", "messages", type_="unique")
    op.drop_column("messages", "widget_idempotency_hash")
    op.drop_constraint("ck_tickets_source", "tickets", type_="check")
    op.drop_column("tickets", "source")
