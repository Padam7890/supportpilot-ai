"""Record shopper consent for transactional order-verification email."""

import sqlalchemy as sa
from alembic import op

revision = "0021_widget_order_consent"
down_revision = "0020_widget_cancel_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "widget_order_verifications",
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("widget_order_verifications", "consented_at")
