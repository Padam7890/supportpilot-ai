"""RAG composer migration tests (execution requires backend dependencies)."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.conversation_response_composer import ComposedAnswer
from app.features.ai.application.guarded_generation import generate_guarded_draft


def _args() -> dict:
    return dict(
        organization_id=uuid4(), execution_id=uuid4(),
        execution_kind="widget_reply", question="What is the return policy?",
        instructions=None, transcript=[], context=[{"excerpt": "Returns accepted within 14 days."}],
        integration_context=None, citations=[{"document_id": str(uuid4())}],
        outcomes=[], auto_reply=True, correlation_id=None,
    )


@pytest.mark.asyncio
async def test_knowledge_only_widget_uses_new_composer() -> None:
    with (
        patch(
            "app.features.ai.application.guarded_generation.compose_natural_answer",
            new_callable=AsyncMock,
            return_value=ComposedAnswer(
                text="Returns are accepted within 14 days.",
                usage={}, model_name="test",
            ),
        ) as compose,
        patch(
            "app.features.ai.application.guarded_generation.create_grounded_draft",
            new_callable=AsyncMock,
        ) as old,
    ):
        result = await generate_guarded_draft(**_args())
    assert result.accepted
    compose.assert_awaited_once()
    old.assert_not_awaited()


@pytest.mark.asyncio
async def test_custom_instructions_preserve_existing_generation_path() -> None:
    args = _args()
    args["instructions"] = "Answer in Nepali."
    with (
        patch(
            "app.features.ai.application.guarded_generation.create_grounded_draft",
            new_callable=AsyncMock,
            return_value={"draft": "Returns accepted within 14 days.", "usage": {}},
        ) as old,
        patch(
            "app.features.ai.application.guarded_generation.compose_natural_answer",
            new_callable=AsyncMock,
        ) as compose,
    ):
        await generate_guarded_draft(**args)
    old.assert_awaited_once()
    compose.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_numeric_answer_is_suppressed() -> None:
    with patch(
        "app.features.ai.application.guarded_generation.compose_natural_answer",
        new_callable=AsyncMock,
        return_value=ComposedAnswer(
            text="Returns accepted within 30 days.", usage={}, model_name="test",
        ),
    ):
        result = await generate_guarded_draft(**_args())
    assert not result.accepted
    assert result.citations == []
