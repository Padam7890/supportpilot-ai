"""Persist merchant-controlled storefront assistant greeting."""

import sqlalchemy as sa
from alembic import op

revision = "0065_widget_greeting_branding"
down_revision = "0064_commerce_action_correlation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "support_widgets",
        sa.Column(
            "assistant_name",
            sa.String(length=60),
            nullable=False,
            server_default="SupportPilot AI",
        ),
    )
    op.add_column(
        "support_widgets",
        sa.Column(
            "welcome_message",
            sa.String(length=240),
            nullable=False,
            server_default="Hi! How can we help?",
        ),
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (
            SELECT 1 FROM support_widgets
            WHERE assistant_name <> 'SupportPilot AI'
               OR welcome_message <> 'Hi! How can we help?'
        ) THEN
            RAISE EXCEPTION 'Refusing to remove customized storefront widget greetings';
        END IF;
        END $$"""
    )
    op.drop_column("support_widgets", "welcome_message")
    op.drop_column("support_widgets", "assistant_name")
