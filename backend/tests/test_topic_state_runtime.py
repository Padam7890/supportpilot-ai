"""Runtime topic state tests: persistence and safe retrieval fallback."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.topic_state_runtime import resolve_and_record_topic


@pytest.mark.asyncio
async def test_explicit_subject_is_saved() -> None:
    db = AsyncMock()
    ids = [uuid4() for _ in range(3)]
    with (
        patch("app.features.ai.application.topic_state_runtime.read_topic_state", new_callable=AsyncMock, return_value=None),
        patch("app.features.ai.application.topic_state_runtime.save_topic_state", new_callable=AsyncMock, return_value=True) as save,
    ):
        query = await resolve_and_record_topic(
            db, organization_id=ids[0], conversation_id=ids[1], agent_id=ids[2],
            message="What is the refund policy?", prior_transcript=[],
            retrieval_query="What is the refund policy?", explicit_topic=True,
        )
        assert query == "What is the refund policy?"
        save.assert_awaited_once()
        assert save.await_args.kwargs["topic"] == "refund"


@pytest.mark.asyncio
async def test_unanchored_followup_recovers_safe_topic_label() -> None:
    ids = [uuid4() for _ in range(3)]
    with (
        patch("app.features.ai.application.topic_state_runtime.read_topic_state", new_callable=AsyncMock,
              return_value=SimpleNamespace(active_topic="delivery", version=2)),
        patch("app.features.ai.application.topic_state_runtime.save_topic_state", new_callable=AsyncMock) as save,
    ):
        query = await resolve_and_record_topic(
            AsyncMock(), organization_id=ids[0], conversation_id=ids[1], agent_id=ids[2],
            message="for Kathmandu?", prior_transcript=[],
            retrieval_query="for Kathmandu?", explicit_topic=False,
        )
        assert query == "delivery for Kathmandu?"
        save.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_unrelated_question_does_not_inherit_old_topic() -> None:
    ids = [uuid4() for _ in range(3)]
    with patch(
        "app.features.ai.application.topic_state_runtime.read_topic_state",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(active_topic="refund", version=2),
    ):
        query = await resolve_and_record_topic(
            AsyncMock(), organization_id=ids[0], conversation_id=ids[1], agent_id=ids[2],
            message="Tell me a joke", prior_transcript=[],
            retrieval_query="Tell me a joke", explicit_topic=False,
        )
        assert query == "Tell me a joke"


@pytest.mark.asyncio
async def test_recent_topic_takes_priority_over_durable_topic() -> None:
    ids = [uuid4() for _ in range(3)]
    with patch(
        "app.features.ai.application.topic_state_runtime.read_topic_state",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(active_topic="refund", version=2),
    ):
        query = await resolve_and_record_topic(
            AsyncMock(), organization_id=ids[0], conversation_id=ids[1], agent_id=ids[2],
            message="what about that?",
            prior_transcript=[{"sender": "customer", "content": "Tell me about delivery"}],
            retrieval_query="Tell me about delivery what about that?", explicit_topic=False,
        )
        assert query == "Tell me about delivery what about that?"
