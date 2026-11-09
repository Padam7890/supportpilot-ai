"""Track document content revision and chunk hashes for idempotent embeddings."""

import sqlalchemy as sa
from alembic import op

revision = "0070_embedding_content_revision"
down_revision = "0069_hybrid_semantic_rag"
branch_labels = None
depends_on = None

_PENDING_REVISION = "0000000000000000000000000000000000000000000000000000000000000000"


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("content_revision", sa.String(64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "document_embedding_jobs",
        sa.Column("expected_content_revision", sa.String(64), nullable=True),
    )
    op.add_column(
        "document_embedding_jobs",
        sa.Column("worker_token", sa.String(64), nullable=True),
    )

    op.execute(
        sa.text(
            "UPDATE document_chunks SET content_hash = encode(sha256(convert_to(content, 'UTF8')), 'hex')"
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE knowledge_documents AS d
            SET content_revision = agg.revision
            FROM (
                SELECT organization_id, document_id,
                       encode(
                           sha256(
                               convert_to(string_agg(content, E'\\n' ORDER BY chunk_index), 'UTF8')
                           ),
                           'hex'
                       ) AS revision
                FROM document_chunks
                GROUP BY organization_id, document_id
            ) AS agg
            WHERE d.organization_id = agg.organization_id AND d.id = agg.document_id
            """
        )
    )
    op.execute(
        sa.text(
            f"UPDATE knowledge_documents SET content_revision = '{_PENDING_REVISION}' "
            "WHERE content_revision IS NULL"
        )
    )

    op.alter_column("document_chunks", "content_hash", nullable=False)
    op.alter_column("knowledge_documents", "content_revision", nullable=False)

    op.create_index(
        "ix_document_chunks_org_document_hash",
        "document_chunks",
        ["organization_id", "document_id", "content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_org_document_hash", table_name="document_chunks")
    op.drop_column("document_embedding_jobs", "worker_token")
    op.drop_column("document_embedding_jobs", "expected_content_revision")
    op.drop_column("document_chunks", "content_hash")
    op.drop_column("knowledge_documents", "content_revision")
