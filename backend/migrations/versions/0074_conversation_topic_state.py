"""Add bounded, tenant-isolated durable topic state (not identity verification)."""
import sqlalchemy as sa
from alembic import op

revision = "0074_conversation_topic_state"
down_revision = "0073_embedding_source_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_topic_states",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("ai_agent_id", sa.Uuid(), nullable=False),
        sa.Column("active_topic", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "conversation_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            ondelete="CASCADE",
            name="fk_topic_state_org_conversation",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "ai_agent_id"],
            ["ai_agents.organization_id", "ai_agents.id"],
            ondelete="RESTRICT",
            name="fk_topic_state_org_agent",
        ),
        sa.CheckConstraint("version > 0", name="ck_topic_state_version"),
        sa.CheckConstraint(
            "active_topic IN ('refund','delivery','order','product','payment')",
            name="ck_topic_state_topic",
        ),
    )
    op.create_index(
        "ix_topic_state_org_expiry",
        "conversation_topic_states", ["organization_id", "expires_at"],
    )
    op.execute('ALTER TABLE "conversation_topic_states" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "conversation_topic_states" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON conversation_topic_states
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "conversation_topic_states"')
    op.drop_index("ix_topic_state_org_expiry", table_name="conversation_topic_states")
    op.drop_table("conversation_topic_states")
