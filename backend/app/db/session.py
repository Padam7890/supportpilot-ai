from collections.abc import AsyncIterator
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

engine_options = {"pool_pre_ping": True, "echo": settings.debug}
if settings.app_env == "test":
    # AnyIO tests can use a new event loop per test; avoid carrying asyncpg
    # connections between loops through SQLAlchemy's default pool.
    engine_options["poolclass"] = NullPool
else:
    engine_options.update(pool_size=5, max_overflow=10)

engine = create_async_engine(settings.database_url, **engine_options)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def set_tenant_context(session: AsyncSession, organization_id: UUID | str) -> None:
    # Transaction-local: PostgreSQL clears this setting on COMMIT/ROLLBACK.
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tenant_id, true)"),
        {"tenant_id": str(organization_id)},
    )
