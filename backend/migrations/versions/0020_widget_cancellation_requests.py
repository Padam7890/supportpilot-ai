"""Allow storefront shoppers to create pending, human-reviewed order actions."""

import sqlalchemy as sa
from alembic import op

revision = "0020_widget_cancel_requests"
down_revision = "0019_widget_order_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_commerce_actions_pending_shopify_cancel_order",
        "commerce_actions",
        ["organization_id", "shopify_order_id"],
        unique=True,
        postgresql_where=sa.text(
            "provider = 'shopify' AND action_type = 'cancel' AND approval_status = 'pending'"
        ),
    )
    op.alter_column("commerce_actions", "requested_by_user_id", nullable=True)


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM commerce_actions WHERE requested_by_user_id IS NULL) THEN
            RAISE EXCEPTION 'Cannot downgrade: storefront cancellation requests exist';
          END IF;
        END $$"""
    )
    op.alter_column("commerce_actions", "requested_by_user_id", nullable=False)
    op.drop_index("uq_commerce_actions_pending_shopify_cancel_order", table_name="commerce_actions")
