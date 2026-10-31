import pytest

from scripts import provision_ci_database_roles


@pytest.mark.parametrize("value", ["bad-role", "role;drop", "has space", "MixedCase"])
def test_ci_database_role_names_reject_unsafe_identifiers(value):
    with pytest.raises(ValueError):
        provision_ci_database_roles.role_name(value, "APP_DB_USER")


@pytest.mark.anyio
async def test_ci_database_provisioner_uses_separate_runtime_and_migration_roles(monkeypatch, capsys):
    monkeypatch.setenv("CI_SUPERUSER_DATABASE_URL", "postgresql://postgres:secret@localhost/supportpilot")
    monkeypatch.setenv("POSTGRES_DB", "supportpilot")
    monkeypatch.setenv("APP_DB_USER", "supportpilot_app")
    monkeypatch.setenv("APP_DB_PASSWORD", "runtime-secret")
    monkeypatch.setenv("MIGRATION_DB_USER", "supportpilot_migrator")
    monkeypatch.setenv("MIGRATION_DB_PASSWORD", "migration-secret")

    class Connection:
        def __init__(self):
            self.statements = []
            self.closed = False

        async def fetchrow(self, _query, database, app_role, app_password, migrator_role, migrator_password):
            return {
                "database_name": f'"{database}"',
                "app_role": f'"{app_role}"',
                "app_password": f"'{app_password}'",
                "migrator_role": f'"{migrator_role}"',
                "migrator_password": f"'{migrator_password}'",
            }

        async def execute(self, statement):
            self.statements.append(statement)

        async def close(self):
            self.closed = True

    connection = Connection()

    async def connect(url):
        assert url == "postgresql://postgres:secret@localhost/supportpilot"
        return connection

    monkeypatch.setattr(provision_ci_database_roles.asyncpg, "connect", connect)
    await provision_ci_database_roles.main()

    assert any('"supportpilot_app" LOGIN NOBYPASSRLS' in sql for sql in connection.statements)
    assert any('"supportpilot_migrator" LOGIN BYPASSRLS' in sql for sql in connection.statements)
    assert any("ALTER DATABASE \"supportpilot\" OWNER TO \"supportpilot_migrator\"" in sql for sql in connection.statements)
    assert any("ALTER DEFAULT PRIVILEGES FOR ROLE \"supportpilot_migrator\"" in sql for sql in connection.statements)
    assert connection.closed
    output = capsys.readouterr().out
    assert "runtime-secret" not in output
    assert "migration-secret" not in output
    assert "postgresql://" not in output
