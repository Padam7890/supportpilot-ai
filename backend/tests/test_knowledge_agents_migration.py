import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def migration_module():
    path = Path(__file__).parents[1] / "migrations/versions/0036_knowledge_bases_and_ai_agents.py"
    spec = importlib.util.spec_from_file_location("knowledge_agents_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def render(operation) -> str:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql",
        opts={"as_sql": True, "output_buffer": output},
    )
    migration = migration_module()
    migration.op = Operations(context)
    operation(migration)
    return output.getvalue()


def test_knowledge_agent_migration_backfills_defaults_and_preserves_existing_widget_key():
    migration = migration_module()
    upgrade_sql = render(lambda loaded: loaded.upgrade())
    downgrade_sql = render(lambda loaded: loaded.downgrade())

    assert migration.down_revision == "0035_shared_auth_identities"
    assert "INSERT INTO knowledge_bases" in upgrade_sql
    assert "INSERT INTO ai_agents" in upgrade_sql
    assert "INSERT INTO ai_agent_knowledge_bases" in upgrade_sql
    assert "UPDATE knowledge_documents AS documents" in upgrade_sql
    assert "fk_support_widgets_org_agent" in upgrade_sql
    assert "uq_support_widgets_org_id" not in upgrade_sql
    assert "DROP CONSTRAINT uq_support_widgets_org_id" not in downgrade_sql
    assert upgrade_sql.count("CREATE POLICY tenant_isolation") == 3
    assert "Cannot downgrade knowledge bases: workspace-specific configuration exists" in downgrade_sql
    assert "Cannot downgrade AI agents: workspace-specific configuration exists" in downgrade_sql
    assert "Cannot downgrade AI defaults: a workspace default is missing" in downgrade_sql
    assert "Cannot downgrade AI assignments: default assignment was changed" in downgrade_sql
    assert "description IS DISTINCT FROM 'Default knowledge base for existing workspace content'" in downgrade_sql
    assert "description IS DISTINCT FROM 'Default knowledge base for workspace content'" in downgrade_sql
    assert downgrade_sql.index("Cannot downgrade") < downgrade_sql.index("DROP TABLE ai_agents")
    assert "DELETE FROM knowledge_documents" not in upgrade_sql
    assert "DROP TABLE knowledge_documents" not in downgrade_sql
