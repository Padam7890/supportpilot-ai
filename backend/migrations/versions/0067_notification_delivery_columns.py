"""Add missing notification delivery tracking columns."""

from alembic import op


revision = "0067_notification_delivery_columns"
down_revision = "0066_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0066 may already be recorded in databases created from an earlier
    # iteration of that migration. Add the ORM-required columns idempotently.
    op.execute(
        "ALTER TABLE notification_recipients "
        "ADD COLUMN IF NOT EXISTS email_sent_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE notification_recipients "
        "ADD COLUMN IF NOT EXISTS email_attempt_count INTEGER NOT NULL DEFAULT 0"
    )
    op.execute(
        "ALTER TABLE notification_recipients "
        "ADD COLUMN IF NOT EXISTS email_last_error VARCHAR(80)"
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (
            SELECT 1 FROM notification_recipients
            WHERE email_sent_at IS NOT NULL
               OR email_attempt_count > 0
               OR email_last_error IS NOT NULL
        ) THEN
            RAISE EXCEPTION 'Refusing to remove notification delivery history';
        END IF;
        END $$"""
    )
    op.execute("ALTER TABLE notification_recipients DROP COLUMN IF EXISTS email_last_error")
    op.execute("ALTER TABLE notification_recipients DROP COLUMN IF EXISTS email_attempt_count")
    op.execute("ALTER TABLE notification_recipients DROP COLUMN IF EXISTS email_sent_at")
