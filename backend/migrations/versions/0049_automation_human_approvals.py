"""Add durable Owner/Admin review steps to automation executions."""

import sqlalchemy as sa
from alembic import op

revision = "0049_automation_human_approvals"
down_revision = "0048_ai_agent_tool_allowlist"
branch_labels = None
depends_on = None


def _enable_tenant_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY tenant_isolation ON "{table}"
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
    )


def upgrade() -> None:
    op.drop_constraint("ck_automation_executions_status", "automation_executions", type_="check")
    op.create_check_constraint(
        "ck_automation_executions_status",
        "automation_executions",
        "status IN ('queued', 'running', 'waiting_approval', 'succeeded', 'failed', 'rejected')",
    )
    op.create_table(
        "automation_execution_approvals",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("action_index", sa.Integer(), nullable=False),
        sa.Column("summary", sa.String(200), nullable=False),
        sa.Column("detail", sa.String(2000)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reviewed_by_user_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("action_index >= 0", name="ck_automation_execution_approvals_action_index"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_automation_execution_approvals_status"),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_automation_execution_approvals_org", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "execution_id"],
            ["automation_executions.organization_id", "automation_executions.id"],
            name="fk_automation_execution_approvals_org_execution", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reviewed_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_automation_execution_approvals_org_reviewer", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "execution_id", "action_index",
            name="uq_automation_execution_approvals_org_execution_step",
        ),
    )
    op.create_index(
        "ix_automation_execution_approvals_org_status",
        "automation_execution_approvals",
        ["organization_id", "status", "created_at"],
    )
    _enable_tenant_rls("automation_execution_approvals")


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM automation_execution_approvals) THEN
          RAISE EXCEPTION 'Refusing to drop automation approval history';
        END IF;
        END $$"""
    )
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "automation_execution_approvals"')
    op.drop_index(
        "ix_automation_execution_approvals_org_status",
        table_name="automation_execution_approvals",
    )
    op.drop_table("automation_execution_approvals")
    op.drop_constraint("ck_automation_executions_status", "automation_executions", type_="check")
    op.create_check_constraint(
        "ck_automation_executions_status",
        "automation_executions",
        "status IN ('queued', 'running', 'succeeded', 'failed')",
    )
