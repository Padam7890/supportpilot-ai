"""Context normalization and tool-execution boundary scenarios."""

from unittest.mock import AsyncMock

import pytest

from app.features.ai.application.conversation_context_builder import build_agent_input
from app.features.ai.application.conversation_tool_contracts import (
    ToolName,
    ToolRequest,
    ToolResult,
)
from app.features.ai.application.conversation_tool_executor import (
    ToolExecutionContext,
    execute_agent_tools,
)


def test_context_removes_duplicate_latest_customer_turn() -> None:
    context = build_agent_input(
        "Do you have phones?",
        [
            {"sender": "assistant", "content": "How can I help?"},
            {"sender": "customer", "content": "Do you have phones?"},
        ],
        channel="widget",
    )
    assert len(context.history) == 1
    assert context.history[0].sender == "assistant"


def test_context_ignores_internal_notes() -> None:
    context = build_agent_input(
        "Hello",
        [{"sender": "internal_note", "content": "Private operator note"}],
        channel="widget",
    )
    assert context.history == []


@pytest.mark.asyncio
async def test_unauthorized_tool_prevents_all_execution() -> None:
    adapter = AsyncMock(
        return_value=ToolResult(name=ToolName.CATALOG_SEARCH, status="ok")
    )
    with pytest.raises(PermissionError):
        await execute_agent_tools(
            [
                ToolRequest(name=ToolName.CATALOG_SEARCH, query="phones"),
                ToolRequest(name=ToolName.SUPPORT_HANDOFF, query="handoff"),
            ],
            context=ToolExecutionContext(
                allowed_tools=frozenset({ToolName.CATALOG_SEARCH})
            ),
            adapters={ToolName.CATALOG_SEARCH: adapter},
        )
    adapter.assert_not_awaited()


@pytest.mark.asyncio
async def test_authorized_read_only_adapter_executes() -> None:
    adapter = AsyncMock(
        return_value=ToolResult(
            name=ToolName.CATALOG_SEARCH, status="ok", facts=["Phone available"]
        )
    )
    results = await execute_agent_tools(
        [ToolRequest(name=ToolName.CATALOG_SEARCH, query="phones")],
        context=ToolExecutionContext(
            allowed_tools=frozenset({ToolName.CATALOG_SEARCH})
        ),
        adapters={ToolName.CATALOG_SEARCH: adapter},
    )
    assert results[0].facts == ["Phone available"]
    adapter.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_budget_enforced_before_execution() -> None:
    with pytest.raises(ValueError, match="budget"):
        await execute_agent_tools(
            [ToolRequest(name=ToolName.CATALOG_SEARCH, query="phones")] * 4,
            context=ToolExecutionContext(
                allowed_tools=frozenset({ToolName.CATALOG_SEARCH})
            ),
            adapters={},
        )
