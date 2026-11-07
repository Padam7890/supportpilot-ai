"""Add tenant-scoped versioned automation workflows and durable executions."""

import sqlalchemy as sa
from alembic import op

revision = "0038_automation_foundation"
down_revision = "0037_integration_ticket_source"
branch_labels = None
depends_on = None


def _enable_tenant_rls(table: str) -> None:
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'''CREATE POLICY tenant_isolation ON "{table}"
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)'''
    )


def upgrade() -> None:
    op.create_table(
        "automation_workflows",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("draft_definition", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("published_version", sa.Integer()),
        sa.Column("draft_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_automation_workflows_org_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_automation_workflows_org_creator",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('draft', 'active', 'paused')", name="ck_automation_workflows_status"),
        sa.CheckConstraint("published_version IS NULL OR published_version > 0", name="ck_automation_workflows_version"),
        sa.CheckConstraint("draft_version > 0", name="ck_automation_workflows_draft_version"),
    )
    op.create_index("ix_automation_workflows_org_status", "automation_workflows", ["organization_id", "status"])

    op.create_table(
        "automation_workflow_versions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("published_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_automation_workflow_versions_org_id"),
        sa.UniqueConstraint("organization_id", "workflow_id", "version", name="uq_automation_workflow_versions_revision"),
        sa.ForeignKeyConstraint(
            ["organization_id", "workflow_id"],
            ["automation_workflows.organization_id", "automation_workflows.id"],
            name="fk_automation_workflow_versions_org_workflow",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "published_by_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_automation_workflow_versions_org_publisher",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("version > 0", name="ck_automation_workflow_versions_version"),
    )

    op.create_table(
        "automation_executions",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("source_message_id", sa.Uuid(), nullable=False),
        sa.Column("event_key", sa.String(80), nullable=False),
        sa.Column("correlation_id", sa.String(64)),
        sa.Column("lease_token", sa.Uuid()),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("result", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error_code", sa.String(80)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_automation_executions_org_id"),
        sa.UniqueConstraint("organization_id", "workflow_id", "event_key", name="uq_automation_executions_event"),
        sa.ForeignKeyConstraint(
            ["organization_id", "workflow_id"],
            ["automation_workflows.organization_id", "automation_workflows.id"],
            name="fk_automation_executions_org_workflow",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "version_id"],
            ["automation_workflow_versions.organization_id", "automation_workflow_versions.id"],
            name="fk_automation_executions_org_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "conversation_id"],
            ["conversations.organization_id", "conversations.id"],
            name="fk_automation_executions_org_conversation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "ticket_id"],
            ["tickets.organization_id", "tickets.id"],
            name="fk_automation_executions_org_ticket",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "source_message_id"],
            ["messages.organization_id", "messages.id"],
            name="fk_automation_executions_org_message",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status IN ('queued', 'running', 'succeeded', 'failed')", name="ck_automation_executions_status"),
        sa.CheckConstraint("attempt_count >= 0 AND attempt_count <= max_attempts", name="ck_automation_executions_attempts"),
        sa.CheckConstraint("max_attempts > 0", name="ck_automation_executions_max_attempts"),
    )
    op.create_index(
        "ix_automation_executions_queue",
        "automation_executions",
        ["organization_id", "status", "next_attempt_at", "created_at"],
    )
    op.create_index(
        "ix_automation_executions_org_created",
        "automation_executions",
        ["organization_id", "created_at"],
    )
    for table in ("automation_workflows", "automation_workflow_versions", "automation_executions"):
        _enable_tenant_rls(table)


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM automation_executions)
           OR EXISTS (SELECT 1 FROM automation_workflow_versions)
           OR EXISTS (SELECT 1 FROM automation_workflows) THEN
          RAISE EXCEPTION 'Refusing to drop automation history; archive/export it before rollback';
        END IF;
        END $$"""
    )
    for table in ("automation_executions", "automation_workflow_versions", "automation_workflows"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_index("ix_automation_executions_org_created", table_name="automation_executions")
    op.drop_index("ix_automation_executions_queue", table_name="automation_executions")
    op.drop_table("automation_executions")
    op.drop_table("automation_workflow_versions")
    op.drop_index("ix_automation_workflows_org_status", table_name="automation_workflows")
    op.drop_table("automation_workflows")
