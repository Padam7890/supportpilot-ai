"""Record the most recent origin-verified storefront widget load."""

import sqlalchemy as sa
from alembic import op

revision = "0051_widget_load_activity"
down_revision = "0050_conversation_ai_agent_override"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "support_widgets",
        sa.Column("last_widget_load_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("support_widgets", "last_widget_load_at")
