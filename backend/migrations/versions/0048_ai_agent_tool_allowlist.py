"""Add per-bot recommendation tool allowlists and execution snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0048_ai_agent_tool_allowlist"
down_revision = "0047_ai_playground_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    default_tools = '["recommend_products", "compare_products"]'
    op.add_column(
        "ai_agents",
        sa.Column(
            "allowed_tools",
            sa.JSON(),
            nullable=False,
            server_default=sa.text(f"'{default_tools}'"),
        ),
    )
    op.add_column("ai_executions", sa.Column("ai_agent_tools_snapshot", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_executions", "ai_agent_tools_snapshot")
    op.drop_column("ai_agents", "allowed_tools")
