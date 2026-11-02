import importlib.util
from io import StringIO
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations


def migration_module():
    path = Path(__file__).parents[1] / "migrations/versions/0034_catalog_variant_connection_integrity.py"
    spec = importlib.util.spec_from_file_location("phase6_catalog_migration", path)
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


def test_catalog_integrity_migration_has_fail_closed_upgrade_and_reversible_rollback():
    migration = migration_module()
    upgrade_sql = render(lambda loaded: loaded.upgrade())
    downgrade_sql = render(lambda loaded: loaded.downgrade())

    assert migration.down_revision == "0033_message_connection_identity"
    assert "product.connection_id <> variant.connection_id" in upgrade_sql
    assert "RAISE EXCEPTION" in upgrade_sql
    assert "uq_catalog_products_org_id_connection" in upgrade_sql
    assert "fk_catalog_variants_org_product_connection" in upgrade_sql
    assert "DELETE FROM" not in upgrade_sql
    assert "UPDATE catalog_" not in upgrade_sql
    assert "DROP CONSTRAINT fk_catalog_variants_org_product_connection" in downgrade_sql
    assert "DROP CONSTRAINT uq_catalog_products_org_id_connection" in downgrade_sql
