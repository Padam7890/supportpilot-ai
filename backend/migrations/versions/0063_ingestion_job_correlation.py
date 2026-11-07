"""Persist request correlation IDs on document ingestion jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0063_ingestion_job_correlation"
down_revision = "0062_conversation_attachments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_ingestion_jobs",
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_document_ingestion_jobs_org_correlation",
        "document_ingestion_jobs",
        ["organization_id", "correlation_id"],
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM document_ingestion_jobs WHERE correlation_id IS NOT NULL) THEN
          RAISE EXCEPTION 'Refusing to remove stored document ingestion correlation history';
        END IF;
        END $$"""
    )
    op.drop_index(
        "ix_document_ingestion_jobs_org_correlation",
        table_name="document_ingestion_jobs",
    )
    op.drop_column("document_ingestion_jobs", "correlation_id")
