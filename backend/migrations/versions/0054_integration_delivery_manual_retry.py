"""Allow a bounded number of operator retries for failed deliveries."""

import sqlalchemy as sa
from alembic import op

revision = "0054_integration_delivery_manual_retry"
down_revision = "0053_automation_approval_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "integration_delivery_jobs",
        sa.Column("manual_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_integration_delivery_jobs_manual_retry_count",
        "integration_delivery_jobs",
        "manual_retry_count >= 0 AND manual_retry_count <= 3",
    )
    op.alter_column("integration_delivery_jobs", "manual_retry_count", server_default=None)


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (
          SELECT 1 FROM integration_delivery_jobs WHERE manual_retry_count > 0
        ) THEN
          RAISE EXCEPTION 'Refusing to remove outbound delivery retry history';
        END IF;
        END $$"""
    )
    op.drop_constraint(
        "ck_integration_delivery_jobs_manual_retry_count",
        "integration_delivery_jobs",
        type_="check",
    )
    op.drop_column("integration_delivery_jobs", "manual_retry_count")
