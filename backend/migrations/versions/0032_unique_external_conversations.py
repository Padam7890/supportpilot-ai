"""Prevent duplicate provider conversation mappings after validating existing rows."""

from alembic import op

revision = "0032_unique_external_conversations"
down_revision = "0031_integration_event_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (
            SELECT 1 FROM conversations
            WHERE integration_connection_id IS NOT NULL
              AND external_conversation_id IS NOT NULL
            GROUP BY organization_id, integration_connection_id, external_conversation_id
            HAVING count(*) > 1
        ) THEN
            RAISE EXCEPTION 'Duplicate external conversation mappings exist; resolve before migration';
        END IF;
        END $$"""
    )
    op.create_unique_constraint(
        "uq_conversations_provider_external",
        "conversations",
        ["organization_id", "integration_connection_id", "external_conversation_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_conversations_provider_external", "conversations", type_="unique"
    )
