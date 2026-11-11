"""Add tenant-scoped vector storage and durable embedding jobs.

Embeddings are derived data. Downgrade removes only the new derived tables; source
documents, chunks, and ingestion history remain untouched. The shared pgvector
extension is intentionally retained.
"""

import sqlalchemy as sa
from alembic import op

from app.models.knowledge_document import Vector

revision = "0069_hybrid_semantic_rag"
down_revision = "0068_knowledge_audit_event_constraint"
branch_labels = None
depends_on = None


def _tenant_policy(table_name: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY"))
    op.execute(
        sa.text(
            f"""CREATE POLICY tenant_isolation ON {table_name}
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
        )
    )


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    op.create_table(
        "document_embeddings",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        sa.Column("embedding_version", sa.String(64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("dimensions > 0", name="ck_document_embeddings_dimensions"),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id", "chunk_index"],
            [
                "document_chunks.organization_id",
                "document_chunks.document_id",
                "document_chunks.chunk_index",
            ],
            name="fk_document_embeddings_org_chunk",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "document_id",
            "chunk_index",
            "embedding_model",
            "embedding_version",
            name="uq_document_embedding_version",
        ),
    )
    op.create_index(
        "ix_document_embeddings_org_model",
        "document_embeddings",
        ["organization_id", "embedding_model", "embedding_version", "dimensions"],
    )
    _tenant_policy("document_embeddings")

    op.create_table(
        "document_embedding_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        sa.Column("embedding_version", sa.String(64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_document_embedding_jobs_status",
        ),
        sa.CheckConstraint("max_attempts > 0", name="ck_document_embedding_jobs_max_attempts"),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts",
            name="ck_document_embedding_jobs_attempt_count",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["knowledge_documents.organization_id", "knowledge_documents.id"],
            name="fk_document_embedding_jobs_org_document",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "document_id",
            "embedding_model",
            "embedding_version",
            name="uq_document_embedding_job_version",
        ),
    )
    op.create_index(
        "ix_document_embedding_jobs_queue",
        "document_embedding_jobs",
        ["organization_id", "status", "next_attempt_at", "created_at"],
    )
    _tenant_policy("document_embedding_jobs")


def downgrade() -> None:
    op.drop_table("document_embedding_jobs")
    op.drop_table("document_embeddings")
