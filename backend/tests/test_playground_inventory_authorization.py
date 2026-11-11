"""Playground inventory must use the locked execution's assigned agent."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.playground_execution import (
    complete_playground_knowledge_inventory,
)


@pytest.mark.asyncio
async def test_mismatched_agent_rejected_before_inventory_query() -> None:
    db = AsyncMock()
    db.scalar.return_value = SimpleNamespace(ai_agent_id=uuid4())
    session = AsyncMock()
    session.__aenter__.return_value = db
    with (
        patch(
            "app.features.ai.application.playground_execution.SessionLocal",
            return_value=session,
        ),
        patch(
            "app.features.ai.application.playground_execution.set_tenant_context",
            new_callable=AsyncMock,
        ),
        patch(
            "app.features.ai.application.playground_execution.load_knowledge_inventory",
            new_callable=AsyncMock,
        ) as load_inventory,pytest.raises(ValueError, match="agent mismatch")
    ):
        await complete_playground_knowledge_inventory(
            uuid4(), uuid4(), ai_agent_id=uuid4()
        )
    load_inventory.assert_not_awaited()
    db.rollback.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_running_execution_does_not_read_inventory() -> None:
    db = AsyncMock()
    db.scalar.return_value = None
    session = AsyncMock()
    session.__aenter__.return_value = db
    with (
        patch(
            "app.features.ai.application.playground_execution.SessionLocal",
            return_value=session,
        ),
        patch(
            "app.features.ai.application.playground_execution.set_tenant_context",
            new_callable=AsyncMock,
        ),
        patch(
            "app.features.ai.application.playground_execution.load_knowledge_inventory",
            new_callable=AsyncMock,
        ) as load_inventory,
    ):
        await complete_playground_knowledge_inventory(
            uuid4(), uuid4(), ai_agent_id=uuid4()
        )
    load_inventory.assert_not_awaited()
    db.rollback.assert_awaited_once()
