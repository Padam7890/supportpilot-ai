import pytest

from scripts.assert_runtime_db_role import (
    has_read_only_migration_ledger_privileges,
    is_tenant_scoped_policy,
)


def test_runtime_migration_ledger_is_read_only():
    assert has_read_only_migration_ledger_privileges(True, False, False, False, False)
    assert not has_read_only_migration_ledger_privileges(True, True, False, False, False)
    assert not has_read_only_migration_ledger_privileges(True, False, True, False, False)
    assert not has_read_only_migration_ledger_privileges(True, False, False, True, False)
    assert not has_read_only_migration_ledger_privileges(True, False, False, False, True)
    assert not has_read_only_migration_ledger_privileges(False, False, False, False, False)


@pytest.mark.parametrize(
    "expression",
    [
        "organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid",
        "(organization_id = (NULLIF(current_setting('app.current_tenant'::text, true), ''::text))::uuid)",
    ],
)
def test_runtime_rls_verifier_accepts_tenant_scoped_predicates(expression):
    assert is_tenant_scoped_policy(expression)


@pytest.mark.parametrize(
    "expression",
    [
        None,
        "true",
        "organization_id IS NOT NULL",
        "organization_id = current_setting('app.current_tenant', true)",
        "organization_id = NULLIF(current_setting('some.other_setting', true), '')::uuid",
        "organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid OR true",
    ],
)
def test_runtime_rls_verifier_rejects_unscoped_or_fail_open_predicates(expression):
    assert not is_tenant_scoped_policy(expression)
