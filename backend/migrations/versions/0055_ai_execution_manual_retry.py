"""Allow a bounded number of operator retries for failed AI executions."""

import sqlalchemy as sa
from alembic import op

revision = "0055_ai_execution_manual_retry"
down_revision = "0054_integration_delivery_manual_retry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_executions",
        sa.Column("manual_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ai_executions",
        sa.Column("last_manual_retry_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "ai_executions",
        sa.Column("last_manual_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_ai_executions_manual_retry_count",
        "ai_executions",
        "manual_retry_count >= 0 AND manual_retry_count <= 3",
    )
    op.create_check_constraint(
        "ck_ai_executions_manual_retry_metadata",
        "ai_executions",
        "(manual_retry_count = 0 AND last_manual_retry_by_user_id IS NULL AND last_manual_retry_at IS NULL) "
        "OR (manual_retry_count > 0 AND last_manual_retry_by_user_id IS NOT NULL AND last_manual_retry_at IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_ai_executions_org_manual_retry_actor",
        "ai_executions",
        "users",
        ["organization_id", "last_manual_retry_by_user_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.alter_column("ai_executions", "manual_retry_count", server_default=None)


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM ai_executions WHERE manual_retry_count > 0) THEN
          RAISE EXCEPTION 'Refusing to remove AI execution retry history';
        END IF;
        END $$"""
    )
    op.drop_constraint(
        "fk_ai_executions_org_manual_retry_actor",
        "ai_executions",
        type_="foreignkey",
    )
    op.drop_constraint(
        "ck_ai_executions_manual_retry_metadata",
        "ai_executions",
        type_="check",
    )
    op.drop_constraint(
        "ck_ai_executions_manual_retry_count",
        "ai_executions",
        type_="check",
    )
    op.drop_column("ai_executions", "manual_retry_count")
    op.drop_column("ai_executions", "last_manual_retry_by_user_id")
    op.drop_column("ai_executions", "last_manual_retry_at")
