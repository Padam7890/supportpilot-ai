"""Allow a storefront widget to route messages to multiple tenant AI bots."""

import sqlalchemy as sa
from alembic import op

revision = "0043_widget_multiple_ai_agents"
down_revision = "0042_automation_execution_effects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_widget_ai_agents",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("widget_id", sa.Uuid(), nullable=False),
        sa.Column("ai_agent_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "widget_id"],
            ["support_widgets.organization_id", "support_widgets.id"],
            name="fk_support_widget_ai_agents_org_widget",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "ai_agent_id"],
            ["ai_agents.organization_id", "ai_agents.id"],
            name="fk_support_widget_ai_agents_org_agent",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "widget_id", "ai_agent_id",
            name="pk_support_widget_ai_agents",
        ),
    )
    op.create_index(
        "ix_support_widget_ai_agents_org_agent",
        "support_widget_ai_agents",
        ["organization_id", "ai_agent_id"],
    )
    op.execute(
        """INSERT INTO support_widget_ai_agents (organization_id, widget_id, ai_agent_id)
        SELECT organization_id, id, ai_agent_id FROM support_widgets"""
    )
    op.execute('ALTER TABLE "support_widget_ai_agents" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "support_widget_ai_agents" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON support_widget_ai_agents
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM support_widget_ai_agents
                GROUP BY organization_id, widget_id HAVING count(*) > 1
            ) THEN
                RAISE EXCEPTION 'Cannot remove multi-bot widget assignments during downgrade';
            END IF;
        END $$"""
    )
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "support_widget_ai_agents"')
    op.drop_index(
        "ix_support_widget_ai_agents_org_agent", table_name="support_widget_ai_agents"
    )
    op.drop_table("support_widget_ai_agents")
