"""Add tenant-scoped audit history for AI bot configuration changes."""

import sqlalchemy as sa
from alembic import op

revision = "0039_ai_agent_audit"
down_revision = "0038_automation_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_agent_audits",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ai_agent_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("config_version", sa.Integer(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_ai_agent_audits_org_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "ai_agent_id"],
            ["ai_agents.organization_id", "ai_agents.id"],
            name="fk_ai_agent_audits_org_agent",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ai_agent_audits_org_actor",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'updated', 'knowledge_bases_changed', 'activated', 'deactivated')",
            name="ck_ai_agent_audits_event_type",
        ),
        sa.CheckConstraint("config_version > 0", name="ck_ai_agent_audits_config_version"),
    )
    op.create_index(
        "ix_ai_agent_audits_org_agent_time",
        "ai_agent_audits",
        ["organization_id", "ai_agent_id", "created_at", "id"],
    )
    op.execute('ALTER TABLE "ai_agent_audits" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "ai_agent_audits" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON ai_agent_audits
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM ai_agent_audits) THEN
                RAISE EXCEPTION 'Cannot downgrade AI agent audit history while records exist; archive the audit records first';
            END IF;
        END $$"""
    )
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "ai_agent_audits"')
    op.drop_index("ix_ai_agent_audits_org_agent_time", table_name="ai_agent_audits")
    op.drop_table("ai_agent_audits")
