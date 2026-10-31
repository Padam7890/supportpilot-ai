"""Retain knowledge metadata and job history when a document is removed."""

import sqlalchemy as sa
from alembic import op

revision = "0008_knowledge_retention"
down_revision = "0007_internal_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_documents", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_knowledge_documents_org_deleted",
        "knowledge_documents",
        ["organization_id", "deleted_at"],
    )
    op.drop_constraint(
        "ck_document_ingestion_jobs_status", "document_ingestion_jobs", type_="check"
    )
    op.create_check_constraint(
        "ck_document_ingestion_jobs_status",
        "document_ingestion_jobs",
        "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM document_ingestion_jobs WHERE status = 'cancelled') THEN
            RAISE EXCEPTION 'Cannot downgrade: cancelled document job history exists';
          END IF;
        END $$;"""
    )
    op.drop_constraint(
        "ck_document_ingestion_jobs_status", "document_ingestion_jobs", type_="check"
    )
    op.create_check_constraint(
        "ck_document_ingestion_jobs_status",
        "document_ingestion_jobs",
        "status IN ('queued', 'running', 'succeeded', 'failed')",
    )
    op.drop_index("ix_knowledge_documents_org_deleted", table_name="knowledge_documents")
    op.drop_column("knowledge_documents", "deleted_at")
