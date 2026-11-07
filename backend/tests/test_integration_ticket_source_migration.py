import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def load_migration():
    path = Path(__file__).parents[1] / "migrations/versions/0037_integration_ticket_source.py"
    spec = importlib.util.spec_from_file_location("integration_ticket_source_migration", path)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def render(operation) -> str:
    output = StringIO()
    context = MigrationContext.configure(
        dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}
    )
    migration = load_migration()
    migration.op = Operations(context)
    operation(migration)
    return output.getvalue()


def test_integration_ticket_source_is_added_without_changing_existing_sources():
    migration = load_migration()
    upgrade_sql = render(lambda loaded: loaded.upgrade())
    downgrade_sql = render(lambda loaded: loaded.downgrade())

    assert migration.down_revision == "0036_knowledge_bases_and_ai_agents"
    assert "source IN ('manual', 'shopify_widget', 'integration')" in upgrade_sql
    assert "source IN ('manual', 'shopify_widget')" in downgrade_sql
    assert "Cannot downgrade while integration-source tickets exist" in downgrade_sql
