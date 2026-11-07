from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.routes.ai_agents import agent_page_out
from app.models import AIAgent


@pytest.mark.anyio
async def test_agent_page_loads_all_knowledge_base_assignments_in_one_query():
    organization_id = uuid4()
    shared_base_id = uuid4()
    now = datetime.now(UTC)
    agents = [
        AIAgent(
            id=uuid4(),
            organization_id=organization_id,
            name=f"Bot {index}",
            system_instructions="",
            status="active",
            config_version=1,
            is_default=index == 0,
            created_at=now,
            updated_at=now,
        )
        for index in range(3)
    ]
    db = AsyncMock()
    db.execute.return_value = [
        (agents[0].id, shared_base_id),
        (agents[1].id, shared_base_id),
    ]

    result = await agent_page_out(db, agents)

    db.execute.assert_awaited_once()
    assert [item.knowledge_base_ids for item in result] == [
        [shared_base_id],
        [shared_base_id],
        [],
    ]


@pytest.mark.anyio
async def test_empty_agent_page_does_not_query_assignments():
    db = AsyncMock()

    assert await agent_page_out(db, []) == []
    db.execute.assert_not_awaited()
