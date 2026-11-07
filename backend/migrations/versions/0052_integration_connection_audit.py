"""Persist secret-free integration connection lifecycle events."""

import sqlalchemy as sa
from alembic import op

revision = "0052_integration_connection_audit"
down_revision = "0051_widget_load_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_connection_audits",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("provider_id", sa.String(48), nullable=False),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_integration_connection_audits_org_connection",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_integration_connection_audits_org_actor",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "id", name="uq_integration_connection_audits_org_id"
        ),
        sa.CheckConstraint(
            "event_type IN ('connected', 'reauthorized', 'disconnected')",
            name="ck_integration_connection_audits_event_type",
        ),
    )
    op.create_index(
        "ix_integration_connection_audits_org_connection_time",
        "integration_connection_audits",
        ["organization_id", "connection_id", "created_at", "id"],
    )
    op.execute('ALTER TABLE "integration_connection_audits" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "integration_connection_audits" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON integration_connection_audits
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM integration_connection_audits) THEN
                RAISE EXCEPTION 'Cannot downgrade integration connection audit history while records exist';
            END IF;
        END $$"""
    )
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON integration_connection_audits")
    op.drop_index(
        "ix_integration_connection_audits_org_connection_time",
        table_name="integration_connection_audits",
    )
    op.drop_table("integration_connection_audits")
