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


async def set_auth_identity_context(session: AsyncSession, identity_id: UUID | str) -> None:
    """Limit cross-tenant membership discovery to an already verified identity."""
    await session.execute(
        text("SELECT set_config('app.current_identity', :identity_id, true)"),
        {"identity_id": str(identity_id)},
    )


async def set_auth_email_context(session: AsyncSession, email: str) -> None:
    """Restrict unauthenticated identity lookup to the submitted email address."""
    await session.execute(
        text("SELECT set_config('app.auth_email', :email, true)"),
        {"email": email.strip().casefold()},
    )


async def set_auth_challenge_context(session: AsyncSession, token_hash: str) -> None:
    """Scope pre-auth challenge access to the presented unguessable challenge token."""
    await session.execute(
        text("SELECT set_config('app.auth_challenge', :token_hash, true)"),
        {"token_hash": token_hash},
    )
