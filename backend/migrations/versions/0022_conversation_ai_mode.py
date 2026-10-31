"""Allow agents to pause AI replies per storefront conversation."""

import sqlalchemy as sa
from alembic import op

revision = "0022_conversation_ai_mode"
down_revision = "0021_widget_order_consent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("ai_mode", sa.String(length=12), server_default="human", nullable=False),
    )
    op.create_check_constraint(
        "ck_conversations_ai_mode", "conversations", "ai_mode IN ('ai', 'human')"
    )
    # Preserve existing workspace AI configuration for older widget threads.
    op.execute(
        """UPDATE conversations AS c SET ai_mode = 'ai'
        FROM support_widgets AS w
        WHERE c.organization_id = w.organization_id
          AND c.channel = 'shopify_widget' AND w.enabled AND w.ai_enabled"""
    )


def downgrade() -> None:
    op.drop_constraint("ck_conversations_ai_mode", "conversations", type_="check")
    op.drop_column("conversations", "ai_mode")
