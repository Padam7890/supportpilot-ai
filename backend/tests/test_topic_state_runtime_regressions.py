"""Regression tests for initial topic capture and concurrent update handling."""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.topic_state_runtime import resolve_and_record_topic


@pytest.mark.asyncio
async def test_first_explicit_topic_is_persisted() -> None:
    save = AsyncMock(return_value=True)
    with (
        patch("app.features.ai.application.topic_state_runtime.read_topic_state", new=AsyncMock(return_value=None)),
        patch("app.features.ai.application.topic_state_runtime.save_topic_state", new=save),
    ):
        result = await resolve_and_record_topic(
            AsyncMock(), organization_id=uuid4(), conversation_id=uuid4(),
            agent_id=uuid4(), message="What is your refund policy?",
            prior_transcript=[], retrieval_query="refund policy", explicit_topic=False,
        )
    assert result == "refund policy"
    assert save.await_args.kwargs["topic"] == "refund"
    assert save.await_args.kwargs["expected_version"] is None


@pytest.mark.asyncio
async def test_concurrent_conflict_does_not_replace_explicit_query() -> None:
    save = AsyncMock(return_value=False)
    with (
        patch("app.features.ai.application.topic_state_runtime.read_topic_state", new=AsyncMock(return_value=None)),
        patch("app.features.ai.application.topic_state_runtime.save_topic_state", new=save),
    ):
        result = await resolve_and_record_topic(
            AsyncMock(), organization_id=uuid4(), conversation_id=uuid4(),
            agent_id=uuid4(), message="Where is my order?",
            prior_transcript=[], retrieval_query="order tracking", explicit_topic=True,
        )
    assert result == "order tracking"
    save.assert_awaited_once()
