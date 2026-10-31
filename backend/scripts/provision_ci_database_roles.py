"""Provision isolated PostgreSQL roles for CI without mounting the workspace."""

import asyncio
import os
import re

import asyncpg

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def role_name(value: str, variable: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{variable} must be a simple PostgreSQL role identifier")
    return value


async def main() -> None:
    admin_url = os.environ["CI_SUPERUSER_DATABASE_URL"]
    database_name = role_name(os.environ.get("POSTGRES_DB", "supportpilot"), "POSTGRES_DB")
    app_role = role_name(os.environ["APP_DB_USER"], "APP_DB_USER")
    app_password = os.environ["APP_DB_PASSWORD"]
    migrator_role = role_name(os.environ["MIGRATION_DB_USER"], "MIGRATION_DB_USER")
    migrator_password = os.environ["MIGRATION_DB_PASSWORD"]

    connection = await asyncpg.connect(admin_url)
    try:
        # Ask PostgreSQL to quote all dynamic identifiers and password literals.
        quoted = await connection.fetchrow(
            """SELECT quote_ident($1) AS database_name,
                      quote_ident($2) AS app_role,
                      quote_literal($3) AS app_password,
                      quote_ident($4) AS migrator_role,
                      quote_literal($5) AS migrator_password""",
            database_name,
            app_role,
            app_password,
            migrator_role,
            migrator_password,
        )
        await connection.execute(
            f"CREATE ROLE {quoted['app_role']} LOGIN NOBYPASSRLS PASSWORD {quoted['app_password']}"
        )
        await connection.execute(
            f"CREATE ROLE {quoted['migrator_role']} LOGIN BYPASSRLS PASSWORD {quoted['migrator_password']}"
        )
        await connection.execute(
            f"ALTER DATABASE {quoted['database_name']} OWNER TO {quoted['migrator_role']}"
        )
        await connection.execute(
            f"GRANT CONNECT ON DATABASE {quoted['database_name']} TO {quoted['app_role']}"
        )
        await connection.execute(f"GRANT USAGE ON SCHEMA public TO {quoted['app_role']}")
        await connection.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {quoted['app_role']}"
        )
        await connection.execute(
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted['app_role']}"
        )
        await connection.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quoted['migrator_role']} IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {quoted['app_role']}"
        )
        await connection.execute(
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {quoted['migrator_role']} IN SCHEMA public "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {quoted['app_role']}"
        )
        print("Provisioned isolated non-bypass runtime and migrator roles for CI")
    finally:
        await connection.close()


if __name__ == "__main__":
    asyncio.run(main())
