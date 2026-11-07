import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def load_migration():
    path = Path(__file__).parents[1] / "migrations/versions/0041_automation_canvas_layout.py"
    spec = importlib.util.spec_from_file_location("automation_canvas_layout_migration", path)
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


def test_canvas_layout_migration_is_additive_and_refuses_to_discard_saved_layouts():
    migration = load_migration()
    upgrade_sql = render(lambda loaded: loaded.upgrade())
    downgrade_sql = render(lambda loaded: loaded.downgrade())

    assert migration.down_revision == "0040_ai_execution_agent_snapshot"
    assert "ADD COLUMN draft_canvas_layout JSON" in upgrade_sql
    assert "ADD COLUMN canvas_layout JSON" in upgrade_sql
    assert "Cannot downgrade while automation canvas layouts exist" in downgrade_sql
    assert "DROP COLUMN canvas_layout" in downgrade_sql
