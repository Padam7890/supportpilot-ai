"""Add chunk section and page metadata for structure-aware retrieval."""

import sqlalchemy as sa
from alembic import op

revision = "0071_chunk_metadata"
down_revision = "0070_embedding_content_revision"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("section_label", sa.String(255), nullable=True))
    op.add_column("document_chunks", sa.Column("page_number", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_document_chunks_page_number",
        "document_chunks",
        "page_number IS NULL OR page_number > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_document_chunks_page_number", "document_chunks", type_="check")
    op.drop_column("document_chunks", "page_number")
    op.drop_column("document_chunks", "section_label")
