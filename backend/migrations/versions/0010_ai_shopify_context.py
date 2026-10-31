"""Store verified Shopify context encrypted for AI draft jobs."""

import sqlalchemy as sa
from alembic import op

revision = "0010_ai_shopify_context"
down_revision = "0009_shopify_integration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_executions", sa.Column("integration_context_encrypted", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_executions", "integration_context_encrypted")
