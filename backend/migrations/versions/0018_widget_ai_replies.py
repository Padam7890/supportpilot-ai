"""Add tenant-configurable, queued AI replies for storefront chat."""

import sqlalchemy as sa
from alembic import op

revision = "0018_widget_ai_replies"
down_revision = "0017_shopify_storefront_widget"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "support_widgets",
        sa.Column("ai_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "support_widgets",
        sa.Column("ai_reply_mode", sa.String(20), server_default="draft_only", nullable=False),
    )
    op.create_check_constraint(
        "ck_support_widgets_ai_reply_mode",
        "support_widgets",
        "ai_reply_mode IN ('draft_only', 'auto_reply')",
    )

    op.drop_constraint("ck_ai_executions_kind", "ai_executions", type_="check")
    op.create_check_constraint(
        "ck_ai_executions_kind",
        "ai_executions",
        "kind IN ('playground', 'reply_draft', 'widget_reply')",
    )
    op.alter_column("ai_executions", "requested_by_user_id", nullable=True)
    op.add_column("ai_executions", sa.Column("source_message_id", sa.Uuid(), nullable=True))
    op.add_column("ai_executions", sa.Column("delivery_mode", sa.String(20), nullable=True))
    op.add_column("ai_executions", sa.Column("reply_status", sa.String(20), nullable=True))
    op.create_foreign_key(
        "fk_ai_executions_org_source_message",
        "ai_executions",
        "messages",
        ["organization_id", "source_message_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_ai_executions_widget_source",
        "ai_executions",
        ["organization_id", "source_message_id"],
    )
    op.create_check_constraint(
        "ck_ai_executions_delivery_mode",
        "ai_executions",
        "delivery_mode IS NULL OR delivery_mode IN ('draft_only', 'auto_reply')",
    )
    op.create_check_constraint(
        "ck_ai_executions_reply_status",
        "ai_executions",
        "reply_status IS NULL OR reply_status IN ('processing', 'draft_ready', 'sent', 'escalated', 'failed')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_ai_executions_reply_status", "ai_executions", type_="check")
    op.drop_constraint("ck_ai_executions_delivery_mode", "ai_executions", type_="check")
    op.drop_constraint("uq_ai_executions_widget_source", "ai_executions", type_="unique")
    op.drop_constraint(
        "fk_ai_executions_org_source_message", "ai_executions", type_="foreignkey"
    )
    op.drop_column("ai_executions", "reply_status")
    op.drop_column("ai_executions", "delivery_mode")
    op.drop_column("ai_executions", "source_message_id")
    op.alter_column("ai_executions", "requested_by_user_id", nullable=False)
    op.drop_constraint("ck_ai_executions_kind", "ai_executions", type_="check")
    op.create_check_constraint(
        "ck_ai_executions_kind",
        "ai_executions",
        "kind IN ('playground', 'reply_draft')",
    )
    op.drop_constraint("ck_support_widgets_ai_reply_mode", "support_widgets", type_="check")
    op.drop_column("support_widgets", "ai_reply_mode")
    op.drop_column("support_widgets", "ai_enabled")
