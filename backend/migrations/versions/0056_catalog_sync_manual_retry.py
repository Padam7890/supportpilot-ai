"""Allow bounded operator retries for failed catalog syncs."""

import sqlalchemy as sa
from alembic import op

revision = "0056_catalog_sync_manual_retry"
down_revision = "0055_ai_execution_manual_retry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "catalog_sync_jobs",
        sa.Column("manual_retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "catalog_sync_jobs",
        sa.Column("last_manual_retry_by_user_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "catalog_sync_jobs",
        sa.Column("last_manual_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_catalog_sync_manual_retry_count",
        "catalog_sync_jobs",
        "manual_retry_count >= 0 AND manual_retry_count <= 3",
    )
    op.create_check_constraint(
        "ck_catalog_sync_manual_retry_metadata",
        "catalog_sync_jobs",
        "(manual_retry_count = 0 AND last_manual_retry_by_user_id IS NULL AND last_manual_retry_at IS NULL) "
        "OR (manual_retry_count > 0 AND last_manual_retry_by_user_id IS NOT NULL AND last_manual_retry_at IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_catalog_sync_jobs_org_manual_retry_actor",
        "catalog_sync_jobs",
        "users",
        ["organization_id", "last_manual_retry_by_user_id"],
        ["organization_id", "id"],
    )
    op.alter_column("catalog_sync_jobs", "manual_retry_count", server_default=None)


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM catalog_sync_jobs WHERE manual_retry_count > 0) THEN
          RAISE EXCEPTION 'Refusing to remove catalog sync retry history';
        END IF;
        END $$"""
    )
    op.drop_constraint(
        "fk_catalog_sync_jobs_org_manual_retry_actor", "catalog_sync_jobs", type_="foreignkey"
    )
    op.drop_constraint(
        "ck_catalog_sync_manual_retry_metadata", "catalog_sync_jobs", type_="check"
    )
    op.drop_constraint("ck_catalog_sync_manual_retry_count", "catalog_sync_jobs", type_="check")
    op.drop_column("catalog_sync_jobs", "last_manual_retry_at")
    op.drop_column("catalog_sync_jobs", "last_manual_retry_by_user_id")
    op.drop_column("catalog_sync_jobs", "manual_retry_count")
