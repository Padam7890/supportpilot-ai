"""Persist tenant-owned knowledge gap occurrences.

Revision ID: 0072_knowledge_gaps
Revises: 0071_nullable_customer_email
"""
import sqlalchemy as sa
from alembic import op

revision = "0072_knowledge_gaps"
down_revision = "0071_nullable_customer_email"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_gaps",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "source_message_id"], ["messages.organization_id", "messages.id"], ondelete="CASCADE", name="fk_knowledge_gap_org_message"),
        sa.UniqueConstraint("organization_id", "source_message_id", name="uq_knowledge_gap_source"),
    )
    op.create_index("ix_knowledge_gaps_org_created", "knowledge_gaps", ["organization_id", "created_at"])
    op.execute("ALTER TABLE knowledge_gaps ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE knowledge_gaps FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY knowledge_gaps_tenant_isolation ON knowledge_gaps
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
    """)


def downgrade() -> None:
    op.drop_table("knowledge_gaps")
