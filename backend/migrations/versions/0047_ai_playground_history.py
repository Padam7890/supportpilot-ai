"""Persist bounded turn context for multi-turn AI bot Playground sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0047_ai_playground_history"
down_revision = "0046_durable_job_correlation_ids"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_executions", sa.Column("playground_history", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_executions", "playground_history")
