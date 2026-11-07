"""Persist workflow-selected AI bot on conversations."""

import sqlalchemy as sa
from alembic import op

revision = "0050_conversation_ai_agent_override"
down_revision = "0049_automation_human_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("ai_agent_override", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM conversations WHERE ai_agent_override IS TRUE) THEN
          RAISE EXCEPTION 'Refusing to drop active conversation AI bot routing overrides';
        END IF;
        END $$"""
    )
    op.drop_column("conversations", "ai_agent_override")
