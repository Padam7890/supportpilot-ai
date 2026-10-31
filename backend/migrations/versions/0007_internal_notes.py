"""Add private teammate notes to conversation messages."""

from alembic import op

revision = "0007_internal_notes"
down_revision = "0006_ai_executions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (
            SELECT 1 FROM messages
            WHERE sender_type NOT IN ('customer', 'agent', 'assistant', 'system', 'internal_note')
          ) THEN
            RAISE EXCEPTION 'Sprint 3 migration stopped: messages contain an unknown sender type';
          END IF;
        END $$;
        """
    )
    op.create_check_constraint(
        "ck_messages_sender_type",
        "messages",
        "sender_type IN ('customer', 'agent', 'assistant', 'system', 'internal_note')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_messages_sender_type", "messages", type_="check")
