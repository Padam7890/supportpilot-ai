"""Failure persistence never updates a missing or non-running execution."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.execution_failure_persistence import persist_execution_failure


@pytest.mark.asyncio
async def test_missing_running_execution_rolls_back() -> None:
    db = AsyncMock()
    db.scalar.return_value = None
    session = AsyncMock()
    session.__aenter__.return_value = db
    with (
        patch(
            "app.features.ai.application.execution_failure_persistence.SessionLocal",
            return_value=session,
        ),
        patch(
            "app.features.ai.application.execution_failure_persistence.set_tenant_context",
            new_callable=AsyncMock,
        ),
    ):
        result = await persist_execution_failure(
            uuid4(), uuid4(), retryable=True,
            failure_code="ai_execution_failed", now=datetime.now(UTC),
        )
    assert result.found is False
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()
