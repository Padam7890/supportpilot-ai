"""Add creation timestamps to refresh sessions for security settings."""

import sqlalchemy as sa
from alembic import op

revision = "0012_refresh_session_created_at"
down_revision = "0011_ai_evaluations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "refresh_sessions",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_refresh_sessions_org_user_created",
        "refresh_sessions",
        ["organization_id", "user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_refresh_sessions_org_user_created", table_name="refresh_sessions")
    op.drop_column("refresh_sessions", "created_at")
