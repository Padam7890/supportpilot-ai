import os

import pytest
from httpx import ASGITransport, AsyncClient

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
