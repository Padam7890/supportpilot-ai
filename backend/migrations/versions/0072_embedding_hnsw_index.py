"""Promote fixed 1536-d vectors and add cosine HNSW when safe."""

import sqlalchemy as sa
from alembic import op

revision = "0072_embedding_hnsw_index"
down_revision = "0071_chunk_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
              IF EXISTS (
                SELECT 1 FROM document_embeddings WHERE dimensions <> 1536 LIMIT 1
              ) THEN
                RETURN;
              END IF;
              ALTER TABLE document_embeddings
                ALTER COLUMN embedding TYPE vector(1536)
                USING embedding::vector(1536);
              CREATE INDEX IF NOT EXISTS ix_document_embeddings_hnsw_cosine
                ON document_embeddings
                USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            EXCEPTION
              WHEN undefined_object OR invalid_parameter_value OR datatype_mismatch THEN
                NULL;
            END $$;
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_document_embeddings_hnsw_cosine"))
