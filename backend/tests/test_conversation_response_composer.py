from unittest.mock import AsyncMock, patch

import pytest

from app.features.ai.application.conversation_agent_contracts import AgentInput
from app.features.ai.application.conversation_response_evidence import ResponseEvidence
from app.features.ai.application.conversation_response_composer import (
    build_answer_messages, compose_natural_answer,
)


def test_composer_marks_missing_store_evidence() -> None:
    messages = build_answer_messages(
        AgentInput(message="Do you have Samsung phones?", channel="widget"),
        ResponseEvidence(),
    )
    assert "no verified store facts" in messages[-1]["content"]
    assert "Never claim a store product" in messages[0]["content"]


@pytest.mark.asyncio
async def test_composer_uses_configured_gateway() -> None:
    with patch(
        "app.features.ai.application.conversation_response_composer.generate_completion",
        new_callable=AsyncMock,
        return_value=("How can I help?", {"prompt_tokens": 12}, "test-model"),
    ) as generate:
        result = await compose_natural_answer(
            AgentInput(message="Hello", channel="widget"),
            ResponseEvidence(),
        )
    assert result.text == "How can I help?"
    generate.assert_awaited_once()
