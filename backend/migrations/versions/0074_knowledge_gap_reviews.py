"""Persist reviewed FAQ submissions and document linkage."""
from alembic import op
import sqlalchemy as sa
revision = "0074_knowledge_gap_reviews"
down_revision = "0073_knowledge_gap_embeddings"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "knowledge_gap_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("gap_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("reviewer_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_ingestion"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "gap_id"], ["knowledge_gaps.organization_id", "knowledge_gaps.id"], ondelete="CASCADE", name="fk_gap_review_gap"),
        sa.ForeignKeyConstraint(["organization_id", "document_id"], ["knowledge_documents.organization_id", "knowledge_documents.id"], ondelete="RESTRICT", name="fk_gap_review_document"),
        sa.ForeignKeyConstraint(["organization_id", "reviewer_id"], ["users.organization_id", "users.id"], name="fk_gap_review_reviewer"),
    )
    op.create_index("ix_gap_reviews_org_gap", "knowledge_gap_reviews", ["organization_id", "gap_id"])
    op.execute("ALTER TABLE knowledge_gap_reviews ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE knowledge_gap_reviews FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY knowledge_gap_reviews_tenant_isolation ON knowledge_gap_reviews
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)""")

def downgrade() -> None:
    op.drop_table("knowledge_gap_reviews")
