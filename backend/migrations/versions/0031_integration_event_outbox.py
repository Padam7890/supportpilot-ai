"""Add provider-neutral webhook intake ledger and outbound delivery outbox."""

import sqlalchemy as sa
from alembic import op

revision = "0031_integration_event_outbox"
down_revision = "0030_widget_reply_idempotency"
branch_labels = None
depends_on = None


def _enable_tenant_rls(table: str) -> None:
    tenant = "organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY tenant_isolation ON "{table}"
        USING ({tenant}) WITH CHECK ({tenant})'''
    )


def upgrade() -> None:
    op.create_table(
        "integration_webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=48), nullable=False),
        sa.Column("external_event_id", sa.String(length=512), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("normalized_payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_integration_webhook_events_org_connection",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "connection_id", "provider_id", "external_event_id",
            name="uq_integration_webhook_events_dedupe",
        ),
    )
    op.create_index(
        "ix_integration_webhook_events_org_created",
        "integration_webhook_events",
        ["organization_id", "created_at"],
    )

    op.create_table(
        "integration_delivery_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="5", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(length=512), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_integration_delivery_jobs_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0 AND attempt_count <= max_attempts",
            name="ck_integration_delivery_jobs_attempts",
        ),
        sa.CheckConstraint("max_attempts > 0", name="ck_integration_delivery_jobs_max_attempts"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "connection_id"],
            ["integration_connections.organization_id", "integration_connections.id"],
            name="fk_integration_delivery_jobs_org_connection",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "message_id"],
            ["messages.organization_id", "messages.id"],
            name="fk_integration_delivery_jobs_org_message",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key_hash",
            name="uq_integration_delivery_jobs_idempotency",
        ),
        sa.UniqueConstraint(
            "organization_id", "message_id", name="uq_integration_delivery_jobs_message"
        ),
    )
    op.create_index(
        "ix_integration_delivery_jobs_queue",
        "integration_delivery_jobs",
        ["organization_id", "status", "next_attempt_at", "created_at"],
    )
    _enable_tenant_rls("integration_webhook_events")
    _enable_tenant_rls("integration_delivery_jobs")


def downgrade() -> None:
    for table in ("integration_delivery_jobs", "integration_webhook_events"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_index("ix_integration_delivery_jobs_queue", table_name="integration_delivery_jobs")
    op.drop_table("integration_delivery_jobs")
    op.drop_index(
        "ix_integration_webhook_events_org_created", table_name="integration_webhook_events"
    )
    op.drop_table("integration_webhook_events")
