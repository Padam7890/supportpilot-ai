"""Add provider identity and delivery metadata to normalized conversations."""

import sqlalchemy as sa
from alembic import op

revision = "0024_normalized_messages"
down_revision = "0023_integration_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("integration_connection_id", sa.Uuid(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("external_conversation_id", sa.String(length=512), nullable=True),
    )
    op.create_foreign_key(
        "fk_conversations_org_integration_connection",
        "conversations",
        "integration_connections",
        ["organization_id", "integration_connection_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_conversations_org_connection_external",
        "conversations",
        ["organization_id", "integration_connection_id", "external_conversation_id"],
    )

    op.add_column("messages", sa.Column("external_message_id", sa.String(length=512)))
    op.add_column("messages", sa.Column("delivery_status", sa.String(length=24)))
    op.add_column(
        "messages",
        sa.Column("provider_metadata", sa.JSON(), server_default="{}", nullable=False),
    )
    op.create_check_constraint(
        "ck_messages_delivery_status",
        "messages",
        "delivery_status IS NULL OR delivery_status IN "
        "('received', 'accepted', 'sent', 'delivered', 'failed', 'unknown')",
    )
    op.create_unique_constraint(
        "uq_messages_provider_external_id",
        "messages",
        ["organization_id", "conversation_id", "external_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_messages_provider_external_id", "messages", type_="unique")
    op.drop_constraint("ck_messages_delivery_status", "messages", type_="check")
    op.drop_column("messages", "provider_metadata")
    op.drop_column("messages", "delivery_status")
    op.drop_column("messages", "external_message_id")
    op.drop_index("ix_conversations_org_connection_external", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_org_integration_connection", "conversations", type_="foreignkey"
    )
    op.drop_column("conversations", "external_conversation_id")
    op.drop_column("conversations", "integration_connection_id")
