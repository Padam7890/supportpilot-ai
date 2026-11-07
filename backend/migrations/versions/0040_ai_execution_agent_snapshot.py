"""Snapshot bot instructions on queued AI executions."""

import sqlalchemy as sa
from alembic import op

revision = "0040_ai_execution_agent_snapshot"
down_revision = "0039_ai_agent_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_executions",
        sa.Column("ai_agent_instructions_snapshot", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    # Do not silently discard bot configuration provenance from executions.
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM ai_executions
                WHERE ai_agent_instructions_snapshot IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade AI execution snapshots while records exist';
            END IF;
        END $$"""
    )
    op.drop_column("ai_executions", "ai_agent_instructions_snapshot")
