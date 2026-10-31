"""Add provider and explicit Shopify cancellation consequences."""

import sqlalchemy as sa
from alembic import op

revision = "0016_shopify_cancel_actions"
down_revision = "0015_commerce_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "commerce_actions",
        sa.Column("provider", sa.String(length=16), server_default="mock", nullable=False),
    )
    op.add_column(
        "commerce_actions",
        sa.Column("cancel_refund", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "commerce_actions",
        sa.Column("cancel_restock", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "commerce_actions",
        sa.Column("cancel_notify_customer", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "commerce_actions",
        sa.Column("cancellation_reason", sa.String(length=20), server_default="CUSTOMER", nullable=False),
    )
    op.create_check_constraint(
        "ck_commerce_actions_provider",
        "commerce_actions",
        "provider IN ('mock', 'shopify')",
    )
    op.create_check_constraint(
        "ck_commerce_actions_provider_type",
        "commerce_actions",
        "provider = 'mock' OR action_type = 'cancel'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_commerce_actions_provider_type", "commerce_actions", type_="check")
    op.drop_constraint("ck_commerce_actions_provider", "commerce_actions", type_="check")
    for column in (
        "cancellation_reason",
        "cancel_notify_customer",
        "cancel_restock",
        "cancel_refund",
        "provider",
    ):
        op.drop_column("commerce_actions", column)
