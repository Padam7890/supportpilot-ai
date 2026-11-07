"""Expire unattended automation approval steps after a review window."""

import sqlalchemy as sa
from alembic import op

revision = "0053_automation_approval_expiry"
down_revision = "0052_integration_connection_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "automation_execution_approvals",
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("now() + interval '7 days'"),
        ),
    )
    op.execute(
        "UPDATE automation_execution_approvals "
        "SET expires_at = now() + interval '7 days' WHERE expires_at IS NULL"
    )
    op.alter_column("automation_execution_approvals", "expires_at", nullable=False)
    op.drop_constraint(
        "ck_automation_execution_approvals_status",
        "automation_execution_approvals",
        type_="check",
    )
    op.create_check_constraint(
        "ck_automation_execution_approvals_status",
        "automation_execution_approvals",
        "status IN ('pending', 'approved', 'rejected', 'expired')",
    )
    op.drop_constraint("ck_automation_executions_status", "automation_executions", type_="check")
    op.create_check_constraint(
        "ck_automation_executions_status",
        "automation_executions",
        "status IN ('queued', 'running', 'waiting_approval', 'succeeded', 'failed', 'rejected', 'expired')",
    )
    op.create_index(
        "ix_automation_approvals_expiry",
        "automation_execution_approvals",
        ["organization_id", "status", "expires_at", "execution_id"],
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM automation_execution_approvals WHERE status = 'expired')
           OR EXISTS (SELECT 1 FROM automation_executions WHERE status = 'expired') THEN
          RAISE EXCEPTION 'Refusing to remove automation approval expiry history';
        END IF;
        END $$"""
    )
    op.drop_index("ix_automation_approvals_expiry", table_name="automation_execution_approvals")
    op.drop_constraint("ck_automation_executions_status", "automation_executions", type_="check")
    op.create_check_constraint(
        "ck_automation_executions_status",
        "automation_executions",
        "status IN ('queued', 'running', 'waiting_approval', 'succeeded', 'failed', 'rejected')",
    )
    op.drop_constraint(
        "ck_automation_execution_approvals_status",
        "automation_execution_approvals",
        type_="check",
    )
    op.create_check_constraint(
        "ck_automation_execution_approvals_status",
        "automation_execution_approvals",
        "status IN ('pending', 'approved', 'rejected')",
    )
    op.drop_column("automation_execution_approvals", "expires_at")
