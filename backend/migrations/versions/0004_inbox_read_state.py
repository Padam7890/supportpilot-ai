"""Add per-user conversation read cursors for inbox unread counts."""

import sqlalchemy as sa
from alembic import op

revision = "0004_inbox_read_state"
down_revision = "0003_platform_approval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_read_states",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_read_message_id", sa.Uuid(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "user_id"],
            ["users.organization_id", "users.id"],
            name="fk_conversation_read_states_org_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_conversation_read_states_org_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id", "user_id", "conversation_id", name="pk_conversation_read_states"
        ),
    )
    op.create_index(
        "ix_conversation_read_states_user_conversation",
        "conversation_read_states",
        ["organization_id", "user_id", "conversation_id"],
    )
    op.execute("ALTER TABLE conversation_read_states ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE conversation_read_states FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation ON conversation_read_states
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )
    op.execute(
        """UPDATE conversations c
           SET updated_at = GREATEST(c.updated_at, COALESCE(m.latest_message_at, c.updated_at))
           FROM (
             SELECT conversation_id, organization_id, MAX(created_at) AS latest_message_at
             FROM messages GROUP BY organization_id, conversation_id
           ) m
           WHERE c.id = m.conversation_id AND c.organization_id = m.organization_id"""
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON conversation_read_states")
    op.drop_index(
        "ix_conversation_read_states_user_conversation", table_name="conversation_read_states"
    )
    op.drop_table("conversation_read_states")
