import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def load_migration():
    path = Path(__file__).parents[1] / "migrations/versions/0038_automation_foundation.py"
    spec = importlib.util.spec_from_file_location("automation_foundation_migration", path)
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


def test_automation_migration_is_tenant_scoped_and_preserves_history_on_downgrade():
    migration = load_migration()
    upgrade_sql = render(lambda loaded: loaded.upgrade())
    downgrade_sql = render(lambda loaded: loaded.downgrade())

    assert migration.down_revision == "0037_integration_ticket_source"
    assert "uq_automation_executions_event" in upgrade_sql
    assert "lease_token UUID" in upgrade_sql
    assert "fk_automation_executions_org_message" in upgrade_sql
    assert upgrade_sql.count("CREATE POLICY tenant_isolation") == 3
    assert "FORCE ROW LEVEL SECURITY" in upgrade_sql
    assert "SKIP LOCKED" not in upgrade_sql
    assert "Refusing to drop automation history" in downgrade_sql
