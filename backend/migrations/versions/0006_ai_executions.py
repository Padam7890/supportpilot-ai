"""Add tenant-owned AI execution records and checkpoint namespace."""

import os
import re

import sqlalchemy as sa
from alembic import op

revision = "0006_ai_executions"
down_revision = "0005_knowledge_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("draft", sa.Text(), nullable=True),
        sa.Column("safe_summary", sa.String(500), nullable=True),
        sa.Column("citations", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("tool_outcomes", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("usage", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("model_name", sa.String(120), nullable=True),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="2", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["organization_id", "requested_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_ai_executions_org_requester",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_ai_executions_org_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "id", name="uq_ai_executions_org_id"),
        sa.CheckConstraint("kind IN ('playground', 'reply_draft')", name="ck_ai_executions_kind"),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_ai_executions_status"),
        sa.CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_ai_executions_attempt_count"),
        sa.CheckConstraint("max_attempts > 0", name="ck_ai_executions_max_attempts"),
    )
    op.create_index("ix_ai_executions_queue", "ai_executions", ["organization_id", "status", "next_attempt_at", "created_at"])
    op.create_index("ix_ai_executions_org_created", "ai_executions", ["organization_id", "created_at"])
    op.execute("ALTER TABLE ai_executions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_executions FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY tenant_isolation ON ai_executions
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )

    # The runtime role may create LangGraph's own tables only in this isolated
    # namespace. Table contents receive RLS in the checkpoint-store initializer.
    app_role = os.environ.get("APP_DB_USER", "supportpilot_app")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", app_role):
        raise ValueError("APP_DB_USER must be a simple PostgreSQL role identifier")
    op.execute("CREATE SCHEMA IF NOT EXISTS supportpilot_checkpoints AUTHORIZATION CURRENT_USER")
    op.execute(f'GRANT USAGE, CREATE ON SCHEMA supportpilot_checkpoints TO "{app_role}"')


def downgrade() -> None:
    op.execute("DROP SCHEMA IF EXISTS supportpilot_checkpoints CASCADE")
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON ai_executions")
    op.drop_index("ix_ai_executions_org_created", table_name="ai_executions")
    op.drop_index("ix_ai_executions_queue", table_name="ai_executions")
    op.drop_table("ai_executions")
