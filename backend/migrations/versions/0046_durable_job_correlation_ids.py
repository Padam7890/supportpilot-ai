"""Persist request correlation references on durable async work."""

import sqlalchemy as sa
from alembic import op

revision = "0046_durable_job_correlation_ids"
down_revision = "0045_catalog_webhook_manual_retry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in (
        "ai_executions",
        "catalog_sync_jobs",
        "catalog_webhook_events",
        "integration_delivery_jobs",
    ):
        op.add_column(table, sa.Column("correlation_id", sa.String(length=64), nullable=True))


def downgrade() -> None:
    for table in (
        "integration_delivery_jobs",
        "catalog_webhook_events",
        "catalog_sync_jobs",
        "ai_executions",
    ):
        op.drop_column(table, "correlation_id")
