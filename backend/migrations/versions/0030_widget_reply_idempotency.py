"""Make widget AI replies idempotent per durable execution."""

import sqlalchemy as sa
from alembic import op

revision = "0030_widget_reply_idempotency"
down_revision = "0029_recommendation_tenant_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("source_ai_execution_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_messages_source_ai_execution",
        "messages",
        "ai_executions",
        ["organization_id", "source_ai_execution_id"],
        ["organization_id", "id"],
    )
    op.create_unique_constraint(
        "uq_messages_org_ai_execution",
        "messages",
        ["organization_id", "source_ai_execution_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_messages_org_ai_execution", "messages", type_="unique")
    op.drop_constraint("fk_messages_source_ai_execution", "messages", type_="foreignkey")
    op.drop_column("messages", "source_ai_execution_id")
