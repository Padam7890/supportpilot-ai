"""Phase 10 topic-state validation; database integration remains a release gate."""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.features.ai.application.durable_topic_state import save_topic_state


@pytest.mark.asyncio
async def test_rejects_unrecognized_topic_before_writing() -> None:
    db = AsyncMock()
    with pytest.raises(ValueError, match="Unsupported conversation topic"):
        await save_topic_state(
            db, organization_id=uuid4(), conversation_id=uuid4(),
            agent_id=uuid4(), topic="otp:123456", expected_version=None,
        )
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_topic_uses_insert_without_overwriting_existing_state() -> None:
    db = AsyncMock()
    db.execute.return_value.rowcount = 0
    created = await save_topic_state(
        db, organization_id=uuid4(), conversation_id=uuid4(),
        agent_id=uuid4(), topic="delivery", expected_version=None,
    )
    assert created is False
    sql = str(db.execute.await_args.args[0]).lower()
    assert "on conflict" in sql
    assert "do update" in sql
    assert "where conversation_topic_states.expires_at <=" in sql


@pytest.mark.asyncio
async def test_versioned_update_uses_compare_and_swap() -> None:
    db = AsyncMock()
    db.execute.return_value.rowcount = 1
    changed = await save_topic_state(
        db, organization_id=uuid4(), conversation_id=uuid4(),
        agent_id=uuid4(), topic="refund", expected_version=3,
    )
    assert changed is True
    sql = str(db.execute.await_args.args[0]).lower()
    assert "version" in sql and "conversation_topic_states" in sql
