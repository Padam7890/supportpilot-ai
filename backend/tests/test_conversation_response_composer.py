"""Catalog adapter and natural composer prompt regression scenarios."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.conversation_catalog_adapter import (
    build_catalog_search_adapter,
)
from app.features.ai.application.conversation_agent_contracts import AgentInput
from app.features.ai.application.conversation_response_evidence import ResponseEvidence
from app.features.ai.application.conversation_response_composer import (
    build_answer_messages, compose_natural_answer,
)
from app.features.ai.application.conversation_tool_contracts import ToolName, ToolRequest


@pytest.mark.asyncio
async def test_catalog_does_not_claim_unrelated_fallback_products() -> None:
    product = type("Product", (), {"title": "Running Shoes", "brand": "Demo", "id": uuid4()})()
    variant = type("Variant", (), {"title": "Size 9", "availability": "available"})()
    candidate = type("Candidate", (), {"product": product, "variant": variant, "searchable_text": "running shoes demo"})()
    session = AsyncMock()
    session.__aenter__.return_value = AsyncMock()
    with (
        patch("app.features.ai.application.conversation_catalog_adapter.SessionLocal", return_value=session),
        patch("app.features.ai.application.conversation_catalog_adapter.set_tenant_context", new_callable=AsyncMock),
        patch("app.features.ai.application.conversation_catalog_adapter.load_candidates", new_callable=AsyncMock) as load,
    ):
        load.return_value = ([candidate], [], [])
        result = await build_catalog_search_adapter(organization_id=uuid4())(
            ToolRequest(name=ToolName.CATALOG_SEARCH, query="Samsung mobile phone")
        )
    assert result.status == "not_found"
    assert not result.facts


def test_composer_marks_missing_store_evidence() -> None:
    messages = build_answer_messages(
        AgentInput(message="Do you have Samsung phones?", channel="widget"),
        ResponseEvidence(context=[], source_ids=[], answerable=False, unavailable=False),
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
            ResponseEvidence(context=[], source_ids=[], answerable=False, unavailable=False),
        )
    assert result.text == "How can I help?"
    generate.assert_awaited_once()
