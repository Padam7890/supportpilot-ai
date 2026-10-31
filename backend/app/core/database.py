from pathlib import Path

from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
EXPECTED_MIGRATION_HEADS = frozenset(ScriptDirectory(str(MIGRATIONS_DIR)).get_heads())


class DatabaseSchemaOutOfDate(RuntimeError):
    """The connected database has not applied the application's current migrations."""


async def check_database() -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
        try:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
        except SQLAlchemyError as exc:
            raise DatabaseSchemaOutOfDate("The database migration version is unavailable") from exc
        applied_heads = frozenset(result.scalars().all())
        if applied_heads != EXPECTED_MIGRATION_HEADS:
            raise DatabaseSchemaOutOfDate("The database schema is behind the application migrations")


async def close_database() -> None:
    await engine.dispose()
