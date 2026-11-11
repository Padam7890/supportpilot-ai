"""Durable reviewer-controlled knowledge gap groups."""
from alembic import op
import sqlalchemy as sa
revision = "0075_knowledge_gap_groups"
down_revision = "0074_knowledge_gap_reviews"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("knowledge_gap_groups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("representative", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", "id", name="uq_knowledge_gap_groups_org_id"))
    op.create_index("ix_knowledge_gap_groups_org", "knowledge_gap_groups", ["organization_id"])
    op.create_table("knowledge_gap_group_members",
        sa.Column("organization_id", sa.Uuid(), primary_key=True),
        sa.Column("group_id", sa.Uuid(), primary_key=True),
        sa.Column("gap_id", sa.Uuid(), primary_key=True),
        sa.ForeignKeyConstraint(["organization_id", "group_id"], ["knowledge_gap_groups.organization_id", "knowledge_gap_groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id", "gap_id"], ["knowledge_gaps.organization_id", "knowledge_gaps.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "gap_id", name="uq_gap_group_one_membership"))
    for table in ("knowledge_gap_groups", "knowledge_gap_group_members"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY {table}_tenant_isolation ON {table}
            USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)""")

def downgrade() -> None:
    op.drop_table("knowledge_gap_group_members")
    op.drop_table("knowledge_gap_groups")
