"""Fail CI if the API is connected with a privileged or non-RLS test role."""

import asyncio
import os
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_TENANT_POLICY_PREDICATE = re.compile(
    r"^\(?\s*organization_id\s*=\s*\(?\s*nullif\s*\(\s*"
    r"current_setting\s*\(\s*'app\.current_tenant'(?:::text)?\s*,\s*true\s*\)\s*,\s*"
    r"''(?:::text)?\s*\)\s*\)?\s*::uuid\s*\)?$",
    re.IGNORECASE,
)

EXPECTED_TENANT_TABLES = frozenset(
    {
        "users",
        "customers",
        "tickets",
        "conversations",
        "messages",
        "refresh_sessions",
        "team_invitations",
        "ticket_activities",
        "ticket_links",
        "conversation_read_states",
        "knowledge_documents",
        "knowledge_document_sources",
        "document_chunks",
        "document_ingestion_jobs",
        "ai_executions",
        "ai_evaluations",
        "shopify_installations",
        "shopify_oauth_states",
        "shopify_access_audit",
        "commerce_actions",
        "commerce_action_audits",
        "support_widgets",
        "widget_order_verifications",
        "widget_submissions",
        "integration_connections",
        "integration_credentials",
        "integration_webhook_events",
        "integration_delivery_jobs",
        "catalog_products",
        "catalog_variants",
        "catalog_sync_jobs",
        "catalog_webhook_events",
        "recommendation_settings",
        "recommendation_events",
        "auth_identity_memberships",
        "auth_challenges",
        "knowledge_bases",
        "ai_agents",
        "ai_agent_audits",
        "ai_agent_knowledge_bases",
        "automation_workflows",
        "automation_workflow_versions",
        "automation_executions",
    }
)


def is_tenant_scoped_policy(expression: str | None) -> bool:
    """Accept only the organization-to-transaction-tenant equality used by our RLS policies."""
    return bool(expression and _TENANT_POLICY_PREDICATE.fullmatch(expression))


def has_read_only_migration_ledger_privileges(
    can_select: bool,
    can_insert: bool,
    can_update: bool,
    can_delete: bool,
    can_truncate: bool,
) -> bool:
    """The runtime role may inspect the Alembic head but cannot change the ledger."""
    return can_select and not any((can_insert, can_update, can_delete, can_truncate))


def has_safe_widget_policies(policies: list[dict[str, str | None]]) -> bool:
    """Validate the public widget lookup policy and tenant-scoped write policies."""
    by_name = {policy["policyname"]: policy for policy in policies}
    public_read = by_name.get("support_widgets_public_read", {}).get("qual") or ""
    public_read_normalized = re.sub(r"\s+", " ", public_read).lower()
    if not (
        "enabled = true" in public_read_normalized
        and " or " in public_read_normalized
        and "current_setting('app.current_tenant'" in public_read_normalized
        and "organization_id" in public_read_normalized
    ):
        return False

    insert_policy = by_name.get("support_widgets_tenant_insert", {})
    update_policy = by_name.get("support_widgets_tenant_update", {})
    delete_policy = by_name.get("support_widgets_tenant_delete", {})
    return (
        insert_policy.get("qual") is None
        and is_tenant_scoped_policy(insert_policy.get("with_check"))
        and is_tenant_scoped_policy(update_policy.get("qual"))
        and is_tenant_scoped_policy(update_policy.get("with_check"))
        and is_tenant_scoped_policy(delete_policy.get("qual"))
    )


def has_safe_auth_policies(table: str, policies: list[dict[str, str | None]]) -> bool:
    """Validate pre-auth data is scoped to an identity or opaque challenge token."""
    by_name = {policy["policyname"]: policy for policy in policies}

    def normalized(expression: str | None) -> str:
        # PostgreSQL adds harmless casts and redundant parentheses when storing
        # policy expressions in pg_policies. Compare predicates, not formatting.
        return (
            re.sub(r"\s+", "", expression or "")
            .lower()
            .replace("::text", "")
            .replace("(", "")
            .replace(")", "")
        )

    if table == "auth_identity_memberships":
        policy = by_name.get("auth_identity_membership_scope", {})
        using = normalized(policy.get("qual"))
        check = normalized(policy.get("with_check"))
        identity = normalized(
            "identity_id = nullif(current_setting('app.current_identity', true), '')::uuid"
        )
        tenant = normalized(
            "organization_id = nullif(current_setting('app.current_tenant', true), '')::uuid"
        )
        return identity in using and tenant in using and identity in check and tenant in check
    if table == "auth_challenges":
        policy = by_name.get("auth_challenge_token_scope", {})
        expected = normalized(
            "token_hash = nullif(current_setting('app.auth_challenge', true), '')"
        )
        using = normalized(policy.get("qual"))
        check = normalized(policy.get("with_check"))
        return expected in using and expected in check
    if table == "auth_identities":
        policy = by_name.get("auth_identity_scope", {})
        using = normalized(policy.get("qual"))
        check = normalized(policy.get("with_check"))
        email = normalized("email_normalized = nullif(current_setting('app.auth_email', true), '')")
        identity = normalized(
            "id = nullif(current_setting('app.current_identity', true), '')::uuid"
        )
        return email in using and identity in using and email in check and identity in check
    return False


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must point at the restricted runtime database role")

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            identity = (
                (
                    await connection.execute(
                        text(
                            """SELECT current_user AS role_name, current_database() AS database_name,
                        role.rolsuper AS is_superuser, role.rolbypassrls AS bypasses_rls
                        FROM pg_roles AS role
                        WHERE role.rolname = current_user"""
                        )
                    )
                )
                .mappings()
                .one()
            )
            expected_role = os.environ.get("EXPECTED_RUNTIME_DB_ROLE", "supportpilot_app")
            expected_database = os.environ.get("EXPECTED_RUNTIME_DB_NAME", "supportpilot")
            if identity["role_name"] != expected_role:
                raise RuntimeError(
                    f"Expected database role {expected_role!r}, got {identity['role_name']!r}"
                )
            if identity["database_name"] != expected_database:
                raise RuntimeError(
                    f"Expected isolated database {expected_database!r}, got {identity['database_name']!r}"
                )
            if identity["is_superuser"] or identity["bypasses_rls"]:
                raise RuntimeError("Runtime database role must not be superuser or BYPASSRLS")

            migration_ledger_privileges = (
                (
                    await connection.execute(
                        text(
                            """SELECT
                        has_table_privilege(current_user, 'public.alembic_version', 'SELECT') AS can_select,
                        has_table_privilege(current_user, 'public.alembic_version', 'INSERT') AS can_insert,
                        has_table_privilege(current_user, 'public.alembic_version', 'UPDATE') AS can_update,
                        has_table_privilege(current_user, 'public.alembic_version', 'DELETE') AS can_delete,
                        has_table_privilege(current_user, 'public.alembic_version', 'TRUNCATE') AS can_truncate"""
                        )
                    )
                )
                .mappings()
                .one()
            )
            if not has_read_only_migration_ledger_privileges(**migration_ledger_privileges):
                raise RuntimeError(
                    "Runtime database role must have SELECT-only access to alembic_version"
                )

            rls_tables = (
                await connection.execute(
                    text(
                        """SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
                        policy.qual AS tenant_using,
                        policy.with_check AS tenant_with_check
                        FROM pg_class AS c
                        JOIN pg_namespace AS n ON n.oid = c.relnamespace
                        LEFT JOIN pg_policies AS policy
                          ON policy.schemaname = n.nspname
                         AND policy.tablename = c.relname
                         AND policy.policyname = 'tenant_isolation'
                        WHERE n.nspname = 'public'
                          AND c.relkind IN ('r', 'p')
                          AND EXISTS (
                            SELECT 1 FROM information_schema.columns AS column_info
                            WHERE column_info.table_schema = n.nspname
                              AND column_info.table_name = c.relname
                              AND column_info.column_name = 'organization_id'
                          )"""
                    )
                )
            ).all()
            actual_tables = {row.relname for row in rls_tables}
            if actual_tables != EXPECTED_TENANT_TABLES:
                raise RuntimeError(
                    f"Expected tenant tables {sorted(EXPECTED_TENANT_TABLES)}, "
                    f"found {sorted(actual_tables)}"
                )
            widget_policies = (
                (
                    await connection.execute(
                        text(
                            "SELECT policyname, qual, with_check FROM pg_policies "
                            "WHERE schemaname = 'public' AND tablename = 'support_widgets'"
                        )
                    )
                )
                .mappings()
                .all()
            )
            if not has_safe_widget_policies([dict(policy) for policy in widget_policies]):
                raise RuntimeError(
                    "Support widget RLS policies must limit public reads to enabled widgets "
                    "and tenant-scope all write policies"
                )
            auth_context_policies = (
                (
                    await connection.execute(
                        text(
                            "SELECT tablename, policyname, qual, with_check FROM pg_policies "
                            "WHERE schemaname = 'public' AND tablename IN "
                            "('auth_identity_memberships', 'auth_challenges', 'auth_identities')"
                        )
                    )
                )
                .mappings()
                .all()
            )
            policies_by_table: dict[str, list[dict[str, str | None]]] = {}
            for policy in auth_context_policies:
                policies_by_table.setdefault(policy["tablename"], []).append(dict(policy))
            if any(
                not has_safe_auth_policies(table, policies_by_table.get(table, []))
                for table in ("auth_identity_memberships", "auth_challenges", "auth_identities")
            ):
                raise RuntimeError(
                    "Pre-authentication data must be restricted to its verified identity "
                    "or opaque challenge token"
                )
            unsafe_tables = [
                row.relname
                for row in rls_tables
                if not row.relrowsecurity
                or not row.relforcerowsecurity
                or (
                    row.relname
                    not in {"support_widgets", "auth_identity_memberships", "auth_challenges"}
                    and (
                        not is_tenant_scoped_policy(row.tenant_using)
                        or not is_tenant_scoped_policy(row.tenant_with_check)
                    )
                )
            ]
            if unsafe_tables:
                raise RuntimeError(
                    "RLS is not enabled, forced, or tenant-scoped for reads and writes on: "
                    + ", ".join(unsafe_tables)
                )

            identity_rls = (
                (
                    await connection.execute(
                        text(
                            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                            "WHERE oid = 'public.auth_identities'::regclass"
                        )
                    )
                )
                .mappings()
                .one()
            )
            if not identity_rls["relrowsecurity"] or not identity_rls["relforcerowsecurity"]:
                raise RuntimeError("Shared auth identities must have forced row-level security")

            print(
                f"Runtime database check passed: {identity['role_name']} on "
                f"{identity['database_name']}, forced RLS verified on {len(rls_tables)} tenant tables, "
                "Alembic migration ledger is read-only"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
