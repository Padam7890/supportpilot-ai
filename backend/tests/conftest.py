import os

import pytest
from httpx import ASGITransport, AsyncClient

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if os.environ.get("CI") and not TEST_DATABASE_URL:
    raise RuntimeError("CI must set TEST_DATABASE_URL to an isolated PostgreSQL test database")
if TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
else:
    # Keep plain pytest runs away from a developer's configured database.
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+asyncpg://invalid:invalid@127.0.0.1:1/supportpilot_test",
    )
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:1/0")
os.environ.setdefault("JWT_SECRET", "pytest-only-secret-that-is-long-enough")
os.environ["APP_ENV"] = "test"

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        # Lifespan-created Redis clients keep loop-bound sockets. Close and
        # clear the app-state client before the next test creates a new loop.
        redis_client = getattr(app.state, "redis", None)
        close = getattr(redis_client, "aclose", None)
        if close is not None:
            await close()
        if redis_client is not None:
            del app.state.redis
