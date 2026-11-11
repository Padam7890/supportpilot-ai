"""Versioned tenant-scoped knowledge gap embedding cache."""
import sqlalchemy as sa
from alembic import op

revision = "0073_knowledge_gap_embeddings"
down_revision = "0072_knowledge_gaps"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_unique_constraint("uq_knowledge_gaps_org_id", "knowledge_gaps", ["organization_id", "id"])
    op.create_table(
        "knowledge_gap_embeddings",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("gap_id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("version", sa.String(60), nullable=False),
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("values", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "gap_id", "model", "version"),
        sa.ForeignKeyConstraint(["organization_id", "gap_id"], ["knowledge_gaps.organization_id", "knowledge_gaps.id"], ondelete="CASCADE", name="fk_gap_embedding_org_gap"),
    )
    op.create_index("ix_gap_embeddings_org_model", "knowledge_gap_embeddings", ["organization_id", "model", "version"])
    op.execute("ALTER TABLE knowledge_gap_embeddings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE knowledge_gap_embeddings FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY knowledge_gap_embeddings_tenant_isolation ON knowledge_gap_embeddings
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)""")

def downgrade() -> None:
    op.drop_table("knowledge_gap_embeddings")
    op.drop_constraint("uq_knowledge_gaps_org_id", "knowledge_gaps", type_="unique")
