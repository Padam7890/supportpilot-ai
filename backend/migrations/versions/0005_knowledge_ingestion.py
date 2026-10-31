"""Add tenant-scoped documents, chunks, and durable ingestion jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0005_knowledge_ingestion"
down_revision = "0004_inbox_read_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "uploaded_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_knowledge_documents_org_uploader",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_knowledge_documents_org_id"),
        sa.CheckConstraint("status IN ('queued', 'processing', 'ready', 'failed')", name="ck_knowledge_documents_status"),
        sa.CheckConstraint("size_bytes > 0", name="ck_knowledge_documents_size"),
    )
    op.create_index("ix_knowledge_documents_org_status", "knowledge_documents", ["organization_id", "status"])
    op.create_table(
        "knowledge_document_sources",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["knowledge_documents.organization_id", "knowledge_documents.id"],
            name="fk_knowledge_document_sources_org_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("organization_id", "document_id"),
        sa.CheckConstraint("octet_length(content) <= 20971520", name="ck_knowledge_source_size"),
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["knowledge_documents.organization_id", "knowledge_documents.id"],
            name="fk_document_chunks_org_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("chunk_index >= 0 AND length(content) > 0", name="ck_document_chunks_content"),
        sa.UniqueConstraint("organization_id", "document_id", "chunk_index", name="uq_document_chunk_index"),
    )
    op.create_index("ix_document_chunks_org_document", "document_chunks", ["organization_id", "document_id"])
    op.execute(
        "CREATE INDEX ix_document_chunks_search ON document_chunks "
        "USING gin (to_tsvector('simple', content))"
    )
    op.create_table(
        "document_ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["knowledge_documents.organization_id", "knowledge_documents.id"],
            name="fk_document_ingestion_jobs_org_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_document_ingestion_jobs_status"),
        sa.CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_document_ingestion_jobs_attempt_count"),
        sa.CheckConstraint("max_attempts > 0", name="ck_document_ingestion_jobs_max_attempts"),
    )
    op.create_index("ix_document_ingestion_jobs_queue", "document_ingestion_jobs", ["organization_id", "status", "next_attempt_at", "created_at"])
    op.create_index("ix_document_ingestion_jobs_org_document", "document_ingestion_jobs", ["organization_id", "document_id"])

    for table in ("knowledge_documents", "knowledge_document_sources", "document_chunks", "document_ingestion_jobs"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
            USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_search")
    for table in ("document_ingestion_jobs", "document_chunks", "knowledge_document_sources", "knowledge_documents"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.drop_table(table)
