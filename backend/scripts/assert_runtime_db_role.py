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


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must point at the restricted runtime database role")

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            identity = (
                await connection.execute(
                    text(
                        """SELECT current_user AS role_name, current_database() AS database_name,
                        role.rolsuper AS is_superuser, role.rolbypassrls AS bypasses_rls
                        FROM pg_roles AS role
                        WHERE role.rolname = current_user"""
                    )
                )
            ).mappings().one()
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
            ).mappings().one()
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
            expected_tables = {
                "users", "customers", "tickets", "conversations", "messages",
                "refresh_sessions", "team_invitations", "ticket_activities",
                "conversation_read_states", "knowledge_documents",
                "knowledge_document_sources", "document_chunks",
                "document_ingestion_jobs", "ai_executions", "ai_evaluations",
                "shopify_installations", "shopify_oauth_states", "shopify_access_audit",
                "commerce_actions", "commerce_action_audits",
                "support_widgets", "widget_order_verifications", "widget_submissions",
            }
            actual_tables = {row.relname for row in rls_tables}
            if actual_tables != expected_tables:
                raise RuntimeError(
                    f"Expected tenant tables {sorted(expected_tables)}, found {sorted(actual_tables)}"
                )
            widget_policies = (
                (
                    await connection.execute(
                        text(
                            "SELECT policyname, qual, with_check FROM pg_policies "
                            "WHERE schemaname = 'public' AND tablename = 'support_widgets'"
                        )
                    )
                ).mappings().all()
            )
            if not has_safe_widget_policies([dict(policy) for policy in widget_policies]):
                raise RuntimeError(
                    "Support widget RLS policies must limit public reads to enabled widgets "
                    "and tenant-scope all write policies"
                )
            unsafe_tables = [
                row.relname
                for row in rls_tables
                if not row.relrowsecurity
                or not row.relforcerowsecurity
                or (
                    row.relname != "support_widgets"
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

            print(
                f"Runtime database check passed: {identity['role_name']} on "
                f"{identity['database_name']}, forced RLS verified on {len(rls_tables)} tenant tables, "
                "Alembic migration ledger is read-only"
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
