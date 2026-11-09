"""Persist source content hash on each stored embedding vector."""

import sqlalchemy as sa
from alembic import op

revision = "0073_embedding_source_hash"
down_revision = "0072_embedding_hnsw_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_embeddings",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE document_embeddings AS e
            SET content_hash = c.content_hash
            FROM document_chunks AS c
            WHERE e.organization_id = c.organization_id
              AND e.document_id = c.document_id
              AND e.chunk_index = c.chunk_index
              AND c.content_hash IS NOT NULL
              AND c.content_hash <> ''
            """
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM document_embeddings
            WHERE content_hash IS NULL OR content_hash = ''
            """
        )
    )
    op.alter_column("document_embeddings", "content_hash", nullable=False)
    op.create_index(
        "ix_document_embeddings_org_doc_hash",
        "document_embeddings",
        ["organization_id", "document_id", "content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_embeddings_org_doc_hash", table_name="document_embeddings")
    op.drop_column("document_embeddings", "content_hash")
