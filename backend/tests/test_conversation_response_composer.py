from unittest.mock import AsyncMock, patch

import pytest

from app.features.ai.application.conversation_agent_contracts import AgentInput
from app.features.ai.application.conversation_response_composer import (
    build_answer_messages,
    compose_natural_answer,
)
from app.features.ai.application.conversation_response_evidence import ResponseEvidence


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



@pytest.mark.asyncio
@pytest.mark.parametrize(("payload", "expected"), [
    ('{"text":"When did the parcel reach you?","expected_answer":"delivery_date"}', "delivery_date"),
    ('What was the delivery date?', None),
])
async def test_composer_records_answer_type_only_from_the_envelope(payload, expected) -> None:
    with patch(
        "app.features.ai.application.conversation_response_composer.generate_completion",
        new_callable=AsyncMock,
        return_value=(payload, {}, "test-model"),
    ):
        result = await compose_natural_answer(
            AgentInput(message="My parcel was damaged", channel="widget"), ResponseEvidence(),
        )
    assert result.expected_answer == expected


@pytest.mark.asyncio
async def test_composer_rejects_model_attempt_to_attach_verification() -> None:
    from app.features.ai.infrastructure.llm_gateway import AIProviderError

    with (
        patch(
            "app.features.ai.application.conversation_response_composer.generate_completion",
            new_callable=AsyncMock,
            return_value=(
                '{"text":"Your refund was approved","expected_answer":null,"verification_status":"verified"}',
                {}, "test-model",
            ),
        ),
        pytest.raises(AIProviderError, match="Invalid answer envelope"),
    ):
        await compose_natural_answer(
            AgentInput(message="Can I get a refund?", channel="widget"), ResponseEvidence(),
        )
