"""Add idempotent, human-reviewed commerce actions and audit history."""

import os
import re

import sqlalchemy as sa
from alembic import op

revision = "0015_commerce_actions"
down_revision = "0014_read_only_migration_ledger"
branch_labels = None
depends_on = None


def _app_role() -> str:
    role = os.environ.get("APP_DB_USER", "supportpilot_app")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", role):
        raise ValueError("APP_DB_USER must be a simple PostgreSQL role identifier")
    return f'"{role}"'


def upgrade() -> None:
    op.create_table(
        "commerce_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(16), nullable=False),
        sa.Column("shopify_order_id", sa.String(120), nullable=False),
        sa.Column("order_number", sa.String(60), nullable=False),
        sa.Column("order_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("refund_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("approval_status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_status", sa.String(20), server_default="not_started", nullable=False),
        sa.Column("execution_attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("execution_result", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("execution_error_code", sa.String(80), nullable=True),
        sa.Column("execution_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action_type IN ('refund', 'cancel')", name="ck_commerce_actions_type"),
        sa.CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')",
            name="ck_commerce_actions_approval_status",
        ),
        sa.CheckConstraint(
            "execution_status IN ('not_started', 'queued', 'running', 'succeeded', 'failed')",
            name="ck_commerce_actions_execution_status",
        ),
        sa.CheckConstraint(
            "(action_type = 'refund' AND refund_amount IS NOT NULL AND refund_amount > 0) "
            "OR (action_type = 'cancel' AND refund_amount IS NULL)",
            name="ck_commerce_actions_amount_matches_type",
        ),
        sa.CheckConstraint(
            "(approval_status IN ('pending', 'rejected', 'expired', 'cancelled') AND execution_status = 'not_started') "
            "OR (approval_status = 'approved' AND execution_status IN ('queued', 'running', 'succeeded', 'failed'))",
            name="ck_commerce_actions_state_pair",
        ),
        sa.CheckConstraint("execution_attempt_count >= 0", name="ck_commerce_actions_attempt_count"),
        sa.CheckConstraint(
            "((approval_status IN ('approved', 'rejected') AND reviewed_by_user_id IS NOT NULL AND reviewed_at IS NOT NULL) "
            "OR (approval_status NOT IN ('approved', 'rejected') AND reviewed_by_user_id IS NULL AND reviewed_at IS NULL))",
            name="ck_commerce_actions_review_metadata",
        ),
        sa.CheckConstraint(
            "((approval_status = 'cancelled' AND cancelled_by_user_id IS NOT NULL AND cancelled_at IS NOT NULL) "
            "OR (approval_status <> 'cancelled' AND cancelled_by_user_id IS NULL AND cancelled_at IS NULL))",
            name="ck_commerce_actions_cancel_metadata",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "ticket_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_commerce_actions_org_ticket",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_commerce_actions_org_requester",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reviewed_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_commerce_actions_org_reviewer",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "cancelled_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_commerce_actions_org_canceller",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_commerce_actions_org_id"),
        sa.UniqueConstraint(
            "organization_id", "idempotency_key_hash", name="uq_commerce_actions_org_idempotency"
        ),
    )
    op.create_index(
        "ix_commerce_actions_queue",
        "commerce_actions",
        ["organization_id", "approval_status", "execution_status", "updated_at"],
    )
    op.create_index(
        "ix_commerce_actions_org_created",
        "commerce_actions",
        ["organization_id", "created_at", "id"],
    )

    op.create_table(
        "commerce_action_audits",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("commerce_action_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("details", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "commerce_action_id"],
            ["commerce_actions.organization_id", "commerce_actions.id"],
            name="fk_commerce_action_audits_org_action",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_commerce_action_audits_org_actor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_commerce_action_audits_org_action_time",
        "commerce_action_audits",
        ["organization_id", "commerce_action_id", "created_at", "id"],
    )

    for table in ("commerce_actions", "commerce_action_audits"):
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'''CREATE POLICY tenant_isolation ON "{table}"
            USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
        )
    op.execute(f"REVOKE UPDATE, DELETE, TRUNCATE ON TABLE commerce_action_audits FROM {_app_role()}")


def downgrade() -> None:
    op.execute(f"GRANT UPDATE, DELETE, TRUNCATE ON TABLE commerce_action_audits TO {_app_role()}")
    for table in ("commerce_action_audits", "commerce_actions"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
        op.drop_table(table)
