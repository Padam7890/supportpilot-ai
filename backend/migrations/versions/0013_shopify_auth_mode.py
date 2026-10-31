"""Track the Shopify token grant used by each store installation."""

import sqlalchemy as sa
from alembic import op

revision = "0013_shopify_auth_mode"
down_revision = "0012_refresh_session_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shopify_installations",
        sa.Column("auth_mode", sa.String(length=32), server_default="oauth", nullable=False),
    )
    op.create_check_constraint(
        "ck_shopify_installations_auth_mode",
        "shopify_installations",
        "auth_mode IN ('oauth', 'client_credentials')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_shopify_installations_auth_mode", "shopify_installations", type_="check")
    op.drop_column("shopify_installations", "auth_mode")
