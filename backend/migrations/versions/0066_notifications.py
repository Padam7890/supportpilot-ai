"""Persist tenant-scoped notifications, recipient state, preferences, and outbox."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0066_notifications"
down_revision = "0065_widget_greeting_branding"
branch_labels = None
depends_on = None


def _tenant_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY tenant_isolation ON "{table}"
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
    )


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(20), server_default="normal", nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("resource_type", sa.String(50)),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action_url", sa.String(500)),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("deduplication_key", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id", "actor_user_id"], ["users.organization_id", "users.id"], ondelete="RESTRICT", name="fk_notifications_org_actor"),
        sa.UniqueConstraint("organization_id", "event_id", name="uq_notifications_org_event"),
        sa.UniqueConstraint("organization_id", "id", name="uq_notifications_org_id"),
        sa.CheckConstraint("category IN ('inbox','ai','automation','integration','knowledge','team','system')", name="ck_notifications_category"),
        sa.CheckConstraint("priority IN ('low','normal','high','critical')", name="ck_notifications_priority"),
    )
    op.create_index("ix_notifications_org_created", "notifications", ["organization_id", sa.text("created_at DESC" )])
    op.create_index("ix_notifications_org_category_created", "notifications", ["organization_id", "category", sa.text("created_at DESC")])
    op.create_index("uq_notifications_org_dedup", "notifications", ["organization_id", "deduplication_key"], unique=True, postgresql_where=sa.text("deduplication_key IS NOT NULL"))

    op.create_table(
        "notification_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("dismissed_at", sa.DateTime(timezone=True)),
        sa.Column("email_sent_at", sa.DateTime(timezone=True)),
        sa.Column("email_attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("email_last_error", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "notification_id"], ["notifications.organization_id", "notifications.id"], ondelete="CASCADE", name="fk_notification_recipients_org_notification"),
        sa.ForeignKeyConstraint(["organization_id", "user_id"], ["users.organization_id", "users.id"], ondelete="CASCADE", name="fk_notification_recipients_org_user"),
        sa.UniqueConstraint("notification_id", "user_id", name="uq_notification_recipients_notification_user"),
    )
    op.create_index("ix_notification_recipients_user_created", "notification_recipients", ["organization_id", "user_id", sa.text("created_at DESC")])
    op.create_index("ix_notification_recipients_unread", "notification_recipients", ["organization_id", "user_id", sa.text("created_at DESC")], postgresql_where=sa.text("read_at IS NULL AND dismissed_at IS NULL"))

    op.create_table(
        "notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("in_app_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id", "user_id"], ["users.organization_id", "users.id"], ondelete="CASCADE", name="fk_notification_preferences_org_user"),
        sa.UniqueConstraint("organization_id", "user_id", "event_type", name="uq_notification_preferences_user_event"),
    )

    op.create_table(
        "notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("organization_id", "event_id", name="uq_notification_outbox_org_event"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_notification_outbox_attempt_count"),
        sa.CheckConstraint("status IN ('pending','running','completed','failed')", name="ck_notification_outbox_status"),
    )
    op.create_index("ix_notification_outbox_claim", "notification_outbox", ["organization_id", "status", "next_attempt_at", "created_at"])

    for table in ("notifications", "notification_recipients", "notification_preferences", "notification_outbox"):
        _tenant_rls(table)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON notification_outbox")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON notification_preferences")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON notification_recipients")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON notifications")
    op.drop_table("notification_outbox")
    op.drop_table("notification_preferences")
    op.drop_table("notification_recipients")
    op.drop_table("notifications")
