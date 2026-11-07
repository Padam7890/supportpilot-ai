"""Add tenant-scoped knowledge-base configuration and source audit history."""

import sqlalchemy as sa
from alembic import op

revision = "0060_knowledge_base_audit"
down_revision = "0059_integration_ai_bot_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_base_audits",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_knowledge_base_audits_org_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "knowledge_base_id"],
            ["knowledge_bases.organization_id", "knowledge_bases.id"],
            name="fk_knowledge_base_audits_org_base",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "actor_user_id"],
            ["users.organization_id", "users.id"],
            name="fk_knowledge_base_audits_org_actor",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "event_type IN ('created', 'updated', 'archived', 'restored', 'default_changed', 'document_moved', 'document_uploaded', 'document_reprocessed', 'document_deleted')",
            name="ck_knowledge_base_audits_event_type",
        ),
    )
    op.create_index(
        "ix_knowledge_base_audits_org_base_time",
        "knowledge_base_audits",
        ["organization_id", "knowledge_base_id", "created_at", "id"],
    )
    op.execute('ALTER TABLE "knowledge_base_audits" ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE "knowledge_base_audits" FORCE ROW LEVEL SECURITY')
    op.execute(
        """CREATE POLICY tenant_isolation ON knowledge_base_audits
        USING (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        WITH CHECK (organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)"""
    )


def downgrade() -> None:
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM knowledge_base_audits) THEN
                RAISE EXCEPTION 'Cannot downgrade knowledge-base audit history while records exist';
            END IF;
        END $$"""
    )
    op.execute('DROP POLICY IF EXISTS tenant_isolation ON "knowledge_base_audits"')
    op.drop_index("ix_knowledge_base_audits_org_base_time", table_name="knowledge_base_audits")
    op.drop_table("knowledge_base_audits")
