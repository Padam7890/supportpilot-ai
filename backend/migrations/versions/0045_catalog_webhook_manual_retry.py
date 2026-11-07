"""Bound operator-initiated retries for failed catalog webhook jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0045_catalog_webhook_manual_retry"
down_revision = "0044_ticket_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_webhook_events",
        sa.Column("manual_retry_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_catalog_webhook_manual_retry_count",
        "catalog_webhook_events",
        "manual_retry_count >= 0 AND manual_retry_count <= 3",
    )
    op.alter_column("catalog_webhook_events", "manual_retry_count", server_default=None)


def downgrade() -> None:
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM catalog_webhook_events WHERE manual_retry_count > 0 LIMIT 1
            ) THEN
                RAISE EXCEPTION 'Cannot remove webhook retry limits while retry history exists';
            END IF;
        END $$"""
    )
    op.drop_constraint(
        "ck_catalog_webhook_manual_retry_count",
        "catalog_webhook_events",
        type_="check",
    )
    op.drop_column("catalog_webhook_events", "manual_retry_count")
