"""Persist request correlation IDs on commerce approval actions."""

import sqlalchemy as sa
from alembic import op

revision = "0064_commerce_action_correlation"
down_revision = "0063_ingestion_job_correlation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commerce_actions",
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_commerce_actions_org_correlation",
        "commerce_actions",
        ["organization_id", "correlation_id"],
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM commerce_actions WHERE correlation_id IS NOT NULL) THEN
          RAISE EXCEPTION 'Refusing to remove commerce action correlation history';
        END IF;
        END $$"""
    )
    op.drop_index("ix_commerce_actions_org_correlation", table_name="commerce_actions")
    op.drop_column("commerce_actions", "correlation_id")
