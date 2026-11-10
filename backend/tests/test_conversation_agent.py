"""Orchestrator security and grounding scenarios (not executed in this session)."""

from unittest.mock import AsyncMock

import pytest

from app.features.ai.application.conversation_agent import run_conversation_agent
from app.features.ai.application.conversation_agent_contracts import AgentDecision, AgentInput
from app.features.ai.application.conversation_response_composer import ComposedAnswer
from app.features.ai.application.conversation_tool_contracts import ToolName, ToolRequest, ToolResult


_INPUT = AgentInput(message="Do you have phones?", channel="widget")


@pytest.mark.asyncio
async def test_read_only_agent_uses_authorized_evidence() -> None:
    planner = AsyncMock(return_value=AgentDecision(
        response_mode="tool",
        tool_requests=[ToolRequest(name=ToolName.CATALOG_SEARCH, query="phones")],
        reasoning_code="catalog_query",
    ))
    adapter = AsyncMock(return_value=ToolResult(
        name=ToolName.CATALOG_SEARCH, status="ok",
        facts=["Phone A is available"], source_ids=["product-a"],
    ))
    composer = AsyncMock(return_value=ComposedAnswer(
        text="Phone A is available.", usage={}, model_name="test",
    ))
    result = await run_conversation_agent(
        _INPUT, planner=planner,
        adapters={ToolName.CATALOG_SEARCH: adapter}, composer=composer,
    )
    assert result.source_ids == ["product-a"]
    adapter.assert_awaited_once()


@pytest.mark.asyncio
async def test_model_cannot_execute_handoff() -> None:
    planner = AsyncMock(return_value=AgentDecision(
        response_mode="tool",
        tool_requests=[ToolRequest(name=ToolName.SUPPORT_HANDOFF, query="escalate")],
        reasoning_code="handoff",
    ))
    with pytest.raises(PermissionError):
        await run_conversation_agent(_INPUT, planner=planner, adapters={})


@pytest.mark.asyncio
async def test_missing_store_evidence_prevents_generation() -> None:
    planner = AsyncMock(return_value=AgentDecision(
        response_mode="tool",
        tool_requests=[ToolRequest(name=ToolName.CATALOG_SEARCH, query="phones")],
        reasoning_code="catalog_query",
    ))
    composer = AsyncMock()
    with pytest.raises(ValueError, match="No verified tool evidence"):
        await run_conversation_agent(
            _INPUT, planner=planner,
            adapters={ToolName.CATALOG_SEARCH: AsyncMock(return_value=ToolResult(
                name=ToolName.CATALOG_SEARCH, status="not_found",
            ))},
            composer=composer,
        )
    composer.assert_not_awaited()


@pytest.mark.asyncio
async def test_numeric_claim_without_evidence_is_blocked() -> None:
    planner = AsyncMock(return_value=AgentDecision(
        response_mode="tool",
        tool_requests=[ToolRequest(name=ToolName.KNOWLEDGE_SEARCH, query="delivery")],
        reasoning_code="policy",
    ))
    composer = AsyncMock(return_value=ComposedAnswer(
        text="Delivery takes 7 days.", usage={}, model_name="test",
    ))
    with pytest.raises(ValueError, match="grounding"):
        await run_conversation_agent(
            _INPUT, planner=planner,
            adapters={ToolName.KNOWLEDGE_SEARCH: AsyncMock(return_value=ToolResult(
                name=ToolName.KNOWLEDGE_SEARCH, status="ok",
                facts=["Delivery time varies."],
            ))},
            composer=composer,
        )
