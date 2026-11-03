import pytest

from scripts.assert_runtime_db_role import (
    has_read_only_migration_ledger_privileges,
    has_safe_auth_policies,
    has_safe_widget_policies,
    is_tenant_scoped_policy,
)


def test_pre_auth_tables_are_scoped_to_identity_or_challenge_token():
    tenant = "organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    identity = "identity_id = NULLIF(current_setting('app.current_identity', true), '')::uuid"
    membership_policies = [
        {
            "policyname": "auth_identity_membership_scope",
            "qual": f"{identity} OR {tenant}",
            "with_check": f"{identity} AND {tenant}",
        }
    ]
    assert has_safe_auth_policies("auth_identity_memberships", membership_policies)

    challenge = "token_hash = NULLIF(current_setting('app.auth_challenge', true), '')"
    challenge_policies = [
        {"policyname": "auth_challenge_token_scope", "qual": challenge, "with_check": challenge}
    ]
    assert has_safe_auth_policies("auth_challenges", challenge_policies)
    challenge_policies[0]["qual"] = "true"
    assert not has_safe_auth_policies("auth_challenges", challenge_policies)

    email = "email_normalized = NULLIF(current_setting('app.auth_email', true), '')"
    identity = "id = NULLIF(current_setting('app.current_identity', true), '')::uuid"
    identity_policies = [
        {"policyname": "auth_identity_scope", "qual": f"{email} OR {identity}", "with_check": f"{email} OR {identity}"}
    ]
    assert has_safe_auth_policies("auth_identities", identity_policies)


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


def test_support_widget_policies_allow_only_enabled_public_lookup_and_tenant_writes():
    tenant = "organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    policies = [
        {
            "policyname": "support_widgets_public_read",
            "qual": f"enabled = true OR ({tenant})",
            "with_check": None,
        },
        {"policyname": "support_widgets_tenant_insert", "qual": None, "with_check": tenant},
        {"policyname": "support_widgets_tenant_update", "qual": tenant, "with_check": tenant},
        {"policyname": "support_widgets_tenant_delete", "qual": tenant, "with_check": None},
    ]
    assert has_safe_widget_policies(policies)

    policies[0]["qual"] = "true"
    assert not has_safe_widget_policies(policies)


def test_support_widget_policies_reject_cross_tenant_writes():
    tenant = "organization_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
    policies = [
        {
            "policyname": "support_widgets_public_read",
            "qual": f"enabled = true OR ({tenant})",
            "with_check": None,
        },
        {"policyname": "support_widgets_tenant_insert", "qual": None, "with_check": tenant},
        {"policyname": "support_widgets_tenant_update", "qual": tenant, "with_check": "true"},
        {"policyname": "support_widgets_tenant_delete", "qual": tenant, "with_check": None},
    ]
    assert not has_safe_widget_policies(policies)
