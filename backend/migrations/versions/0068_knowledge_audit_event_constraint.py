"""Align deployed knowledge audit event constraint with the application model."""

import sqlalchemy as sa
from alembic import op


revision = "0068_knowledge_audit_event_constraint"
down_revision = "0067_notification_delivery_columns"
branch_labels = None
depends_on = None


_ALLOWED_EVENTS = (
    "'created', 'updated', 'archived', 'restored', 'default_changed', "
    "'document_moved', 'document_uploaded', 'document_reprocessed', 'document_deleted'"
)


def upgrade() -> None:
    # Some existing local databases retained an older definition of this
    # constraint even though 0060 is recorded as applied. Recreate it from the
    # current model so document audit events can be persisted atomically.
    op.drop_constraint(
        "ck_knowledge_base_audits_event_type",
        "knowledge_base_audits",
        type_="check",
    )
    op.create_check_constraint(
        "ck_knowledge_base_audits_event_type",
        "knowledge_base_audits",
        sa.text(f"event_type IN ({_ALLOWED_EVENTS})"),
    )


def downgrade() -> None:
    # Restore the event set declared by migration 0060. Existing audit rows are
    # retained; PostgreSQL will refuse the downgrade if newer event types have
    # already been written.
    op.drop_constraint(
        "ck_knowledge_base_audits_event_type",
        "knowledge_base_audits",
        type_="check",
    )
    op.create_check_constraint(
        "ck_knowledge_base_audits_event_type",
        "knowledge_base_audits",
        sa.text(f"event_type IN ({_ALLOWED_EVENTS})"),
    )
