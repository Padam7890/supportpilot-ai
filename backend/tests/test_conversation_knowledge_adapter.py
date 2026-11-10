"""Knowledge adapter and evidence preparation regression scenarios."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.conversation_knowledge_adapter import (
    build_knowledge_search_adapter,
)
from app.features.ai.application.conversation_response_evidence import (
    compose_response_evidence,
)
from app.features.ai.application.conversation_tool_contracts import (
    ToolName,
    ToolRequest,
    ToolResult,
)


@pytest.mark.asyncio
async def test_knowledge_adapter_uses_trusted_scope() -> None:
    organization_id, agent_id = uuid4(), uuid4()
    session = AsyncMock()
    db = AsyncMock()
    session.__aenter__.return_value = db
    with (
        patch(
            "app.features.ai.application.conversation_knowledge_adapter.SessionLocal",
            return_value=session,
        ),
        patch(
            "app.features.ai.application.conversation_knowledge_adapter.set_tenant_context",
            new_callable=AsyncMock,
        ) as tenant,
        patch(
            "app.features.ai.application.conversation_knowledge_adapter.search_agent_knowledge",
            new_callable=AsyncMock,
        ) as search,
    ):
        search.return_value.matches = []
        result = await build_knowledge_search_adapter(
            organization_id=organization_id, ai_agent_id=agent_id
        )(ToolRequest(name=ToolName.KNOWLEDGE_SEARCH, query="returns"))
    assert result.status == "not_found"
    tenant.assert_awaited_once_with(db, organization_id)
    assert search.await_args.kwargs["ai_agent_id"] == agent_id
    assert search.await_args.kwargs["organization_id"] == organization_id


def test_denied_evidence_cannot_become_answerable() -> None:
    evidence = compose_response_evidence([
        ToolResult(
            name=ToolName.ORDER_LOOKUP, status="denied",
            facts=["This private order is shipped"],
        )
    ])
    assert not evidence.answerable
    assert evidence.context == []
    assert evidence.unavailable


def test_evidence_budget_is_enforced() -> None:
    evidence = compose_response_evidence([
        ToolResult(
            name=ToolName.KNOWLEDGE_SEARCH,
            status="ok",
            facts=["x" * 1000],
            source_ids=["doc-1"],
        )
    ], max_characters=120)
    assert len(evidence.context[0]["content"]) == 120
    assert evidence.source_ids == ["doc-1"]
