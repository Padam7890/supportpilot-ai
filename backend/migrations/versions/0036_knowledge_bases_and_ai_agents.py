"""Add tenant-scoped knowledge bases and configurable AI agents."""

import sqlalchemy as sa
from alembic import op

revision = "0036_knowledge_bases_and_ai_agents"
down_revision = "0035_shared_auth_identities"
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
        "knowledge_bases",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_knowledge_bases_org_id"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_knowledge_bases_status"),
    )
    op.create_index("ix_knowledge_bases_org_status", "knowledge_bases", ["organization_id", "status"])
    op.create_index(
        "uq_knowledge_bases_org_default", "knowledge_bases", ["organization_id"],
        unique=True, postgresql_where=sa.text("is_default IS TRUE"),
    )

    op.create_table(
        "ai_agents",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("organization_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("system_instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("config_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("organization_id", "id", name="uq_ai_agents_org_id"),
        sa.CheckConstraint("status IN ('active', 'inactive')", name="ck_ai_agents_status"),
        sa.CheckConstraint("config_version > 0", name="ck_ai_agents_config_version"),
    )
    op.create_index("ix_ai_agents_org_status", "ai_agents", ["organization_id", "status"])
    op.create_index(
        "uq_ai_agents_org_default", "ai_agents", ["organization_id"],
        unique=True, postgresql_where=sa.text("is_default IS TRUE"),
    )
    op.create_table(
        "ai_agent_knowledge_bases",
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("ai_agent_id", sa.Uuid(), nullable=False),
        sa.Column("knowledge_base_id", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("organization_id", "ai_agent_id", "knowledge_base_id"),
        sa.ForeignKeyConstraint(
            ["organization_id", "ai_agent_id"], ["ai_agents.organization_id", "ai_agents.id"],
            name="fk_ai_agent_knowledge_bases_org_agent", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "knowledge_base_id"], ["knowledge_bases.organization_id", "knowledge_bases.id"],
            name="fk_ai_agent_knowledge_bases_org_base", ondelete="CASCADE",
        ),
    )
    op.create_index("ix_ai_agent_knowledge_bases_org_base", "ai_agent_knowledge_bases", ["organization_id", "knowledge_base_id"])

    for table in ("knowledge_documents", "support_widgets", "conversations", "ai_executions"):
        column = "knowledge_base_id" if table == "knowledge_documents" else "ai_agent_id"
        op.add_column(table, sa.Column(column, sa.Uuid(), nullable=True))
    op.add_column("ai_executions", sa.Column("ai_agent_config_version", sa.Integer(), nullable=True))

    op.execute(
        """INSERT INTO knowledge_bases (id, organization_id, name, description, status, is_default)
        SELECT gen_random_uuid(), id, 'General', 'Default knowledge base for existing workspace content', 'active', TRUE
        FROM organizations"""
    )
    op.execute(
        """INSERT INTO ai_agents (id, organization_id, name, system_instructions, status, config_version, is_default)
        SELECT gen_random_uuid(), id, 'SupportPilot Assistant', '', 'active', 1, TRUE
        FROM organizations"""
    )
    op.execute(
        """INSERT INTO ai_agent_knowledge_bases (organization_id, ai_agent_id, knowledge_base_id)
        SELECT agents.organization_id, agents.id, bases.id
        FROM ai_agents AS agents JOIN knowledge_bases AS bases
          ON bases.organization_id = agents.organization_id AND bases.is_default"""
    )
    op.execute(
        """UPDATE knowledge_documents AS documents SET knowledge_base_id = bases.id
        FROM knowledge_bases AS bases
        WHERE bases.organization_id = documents.organization_id AND bases.is_default"""
    )
    for table in ("support_widgets", "conversations", "ai_executions"):
        op.execute(
            f'''UPDATE "{table}" AS target SET ai_agent_id = agents.id
            FROM ai_agents AS agents
            WHERE agents.organization_id = target.organization_id AND agents.is_default'''
        )
    op.execute(
        """UPDATE ai_executions AS executions SET ai_agent_config_version = agents.config_version
        FROM ai_agents AS agents
        WHERE agents.organization_id = executions.organization_id AND agents.is_default"""
    )

    op.alter_column("knowledge_documents", "knowledge_base_id", nullable=False)
    for table in ("support_widgets", "conversations", "ai_executions"):
        op.alter_column(table, "ai_agent_id", nullable=False)
    op.alter_column("ai_executions", "ai_agent_config_version", nullable=False)
    op.create_foreign_key(
        "fk_knowledge_documents_org_knowledge_base", "knowledge_documents", "knowledge_bases",
        ["organization_id", "knowledge_base_id"], ["organization_id", "id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_support_widgets_org_agent", "support_widgets", "ai_agents",
        ["organization_id", "ai_agent_id"], ["organization_id", "id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_conversations_org_agent", "conversations", "ai_agents",
        ["organization_id", "ai_agent_id"], ["organization_id", "id"], ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_ai_executions_org_agent", "ai_executions", "ai_agents",
        ["organization_id", "ai_agent_id"], ["organization_id", "id"], ondelete="RESTRICT",
    )
    op.create_index("ix_knowledge_documents_org_base_status", "knowledge_documents", ["organization_id", "knowledge_base_id", "status"])

    for table in ("knowledge_bases", "ai_agents", "ai_agent_knowledge_bases"):
        _tenant_rls(table)


def downgrade() -> None:
    # This migration adds tenant configuration as well as nullable references
    # that become required after backfill. Refuse rollback once a workspace has
    # customized the defaults; dropping these tables would otherwise erase
    # configuration that cannot be reconstructed by the pre-migration app.
    op.execute(
        """DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM organizations AS organizations
                WHERE NOT EXISTS (
                    SELECT 1 FROM knowledge_bases AS bases
                    WHERE bases.organization_id = organizations.id AND bases.is_default IS TRUE
                )
                OR NOT EXISTS (
                    SELECT 1 FROM ai_agents AS agents
                    WHERE agents.organization_id = organizations.id AND agents.is_default IS TRUE
                )
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade AI defaults: a workspace default is missing';
            END IF;
            IF EXISTS (
                SELECT 1 FROM knowledge_bases
                WHERE is_default IS FALSE
                   OR name <> 'General'
                   OR (
                       description IS DISTINCT FROM 'Default knowledge base for existing workspace content'
                       AND description IS DISTINCT FROM 'Default knowledge base for workspace content'
                   )
                   OR status <> 'active'
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade knowledge bases: workspace-specific configuration exists';
            END IF;
            IF EXISTS (
                SELECT 1 FROM ai_agents
                WHERE is_default IS FALSE
                   OR name <> 'SupportPilot Assistant'
                   OR system_instructions <> ''
                   OR status <> 'active'
                   OR config_version <> 1
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade AI agents: workspace-specific configuration exists';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM ai_agent_knowledge_bases AS assignments
                JOIN ai_agents AS agents
                  ON agents.organization_id = assignments.organization_id
                 AND agents.id = assignments.ai_agent_id
                JOIN knowledge_bases AS bases
                  ON bases.organization_id = assignments.organization_id
                 AND bases.id = assignments.knowledge_base_id
                WHERE agents.is_default IS FALSE OR bases.is_default IS FALSE
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade AI assignments: non-default assignment exists';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM ai_agents AS agents
                JOIN knowledge_bases AS bases
                  ON bases.organization_id = agents.organization_id
                 AND bases.is_default IS TRUE
                WHERE agents.is_default IS TRUE
                  AND NOT EXISTS (
                      SELECT 1 FROM ai_agent_knowledge_bases AS assignments
                      WHERE assignments.organization_id = agents.organization_id
                        AND assignments.ai_agent_id = agents.id
                        AND assignments.knowledge_base_id = bases.id
                  )
            ) THEN
                RAISE EXCEPTION 'Cannot downgrade AI assignments: default assignment was changed';
            END IF;
            IF EXISTS (SELECT 1 FROM ai_executions WHERE ai_agent_config_version <> 1) THEN
                RAISE EXCEPTION 'Cannot downgrade AI executions: configuration history exists';
            END IF;
        END $$"""
    )
    for table in ("ai_agent_knowledge_bases", "ai_agents", "knowledge_bases"):
        op.execute(f'DROP POLICY IF EXISTS tenant_isolation ON "{table}"')
    op.drop_index("ix_knowledge_documents_org_base_status", table_name="knowledge_documents")
    op.drop_constraint("fk_ai_executions_org_agent", "ai_executions", type_="foreignkey")
    op.drop_column("ai_executions", "ai_agent_config_version")
    op.drop_constraint("fk_conversations_org_agent", "conversations", type_="foreignkey")
    op.drop_constraint("fk_support_widgets_org_agent", "support_widgets", type_="foreignkey")
    op.drop_constraint("fk_knowledge_documents_org_knowledge_base", "knowledge_documents", type_="foreignkey")
    for table in ("ai_executions", "conversations", "support_widgets"):
        op.drop_column(table, "ai_agent_id")
    op.drop_column("knowledge_documents", "knowledge_base_id")
    op.drop_index("ix_ai_agent_knowledge_bases_org_base", table_name="ai_agent_knowledge_bases")
    op.drop_table("ai_agent_knowledge_bases")
    op.drop_index("uq_ai_agents_org_default", table_name="ai_agents")
    op.drop_index("ix_ai_agents_org_status", table_name="ai_agents")
    op.drop_table("ai_agents")
    op.drop_index("uq_knowledge_bases_org_default", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_bases_org_status", table_name="knowledge_bases")
    op.drop_table("knowledge_bases")
