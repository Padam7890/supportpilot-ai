"""Bind normalized messages to provider connections for account-scoped idempotency."""

import sqlalchemy as sa
from alembic import op

revision = "0033_message_connection_identity"
down_revision = "0032_unique_external_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("integration_connection_id", sa.Uuid(), nullable=True))
    op.create_unique_constraint(
        "uq_conversations_org_id_connection",
        "conversations",
        ["organization_id", "id", "integration_connection_id"],
    )
    op.create_foreign_key(
        "fk_messages_org_integration_connection",
        "messages",
        "integration_connections",
        ["organization_id", "integration_connection_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_messages_org_conversation_connection",
        "messages",
        "conversations",
        ["organization_id", "conversation_id", "integration_connection_id"],
        ["organization_id", "id", "integration_connection_id"],
        ondelete="CASCADE",
    )
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (
            SELECT 1 FROM messages
            WHERE integration_connection_id IS NOT NULL
              AND external_message_id IS NOT NULL
            GROUP BY organization_id, integration_connection_id, external_message_id
            HAVING count(*) > 1
        ) THEN
            RAISE EXCEPTION 'Duplicate provider message IDs exist; resolve before migration';
        END IF;
        END $$"""
    )
    op.drop_constraint("uq_messages_provider_external_id", "messages", type_="unique")
    op.create_unique_constraint(
        "uq_messages_provider_external_id",
        "messages",
        ["organization_id", "integration_connection_id", "external_message_id"],
    )
    op.create_unique_constraint(
        "uq_messages_org_id_connection",
        "messages",
        ["organization_id", "id", "integration_connection_id"],
    )
    op.create_foreign_key(
        "fk_integration_delivery_jobs_message_connection",
        "integration_delivery_jobs",
        "messages",
        ["organization_id", "message_id", "connection_id"],
        ["organization_id", "id", "integration_connection_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_messages_org_connection_external",
        "messages",
        ["organization_id", "integration_connection_id", "external_message_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_integration_delivery_jobs_message_connection",
        "integration_delivery_jobs",
        type_="foreignkey",
    )
    op.drop_constraint("uq_messages_org_id_connection", "messages", type_="unique")
    op.drop_index("ix_messages_org_connection_external", table_name="messages")
    op.drop_constraint("uq_messages_provider_external_id", "messages", type_="unique")
    op.create_unique_constraint(
        "uq_messages_provider_external_id",
        "messages",
        ["organization_id", "conversation_id", "external_message_id"],
    )
    op.drop_constraint("fk_messages_org_conversation_connection", "messages", type_="foreignkey")
    op.drop_constraint("fk_messages_org_integration_connection", "messages", type_="foreignkey")
    op.drop_constraint("uq_conversations_org_id_connection", "conversations", type_="unique")
    op.drop_column("messages", "integration_connection_id")
