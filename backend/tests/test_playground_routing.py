"""Playground routing preserves deterministic-first behavior."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.features.ai.application.conversation_orchestration import CustomerTurnPlan
from app.features.ai.application.playground_routing import route_playground_conversation


@pytest.mark.asyncio
async def test_deterministic_playground_turn_skips_model_router() -> None:
    with (
        patch(
            "app.features.ai.application.playground_routing.plan_playground_turn",
            return_value=CustomerTurnPlan(
                route="direct", draft="Hello", safe_summary="Greeting", tool_name="greeting",
            ),
        ),
        patch(
            "app.features.ai.application.playground_routing.finish_deterministic_ai_execution",
            new_callable=AsyncMock,
        ) as finish,
        patch(
            "app.features.ai.application.playground_routing.resolve_customer_routing",
            new_callable=AsyncMock,
        ) as router,
    ):
        result = await route_playground_conversation(
            uuid4(), uuid4(), question="hello", transcript=[]
        )
    assert result.completed is True
    finish.assert_awaited_once()
    router.assert_not_awaited()


@pytest.mark.asyncio
async def test_unresolved_playground_turn_uses_playground_channel() -> None:
    routing = AsyncMock()
    routing.tool_outcome = lambda: {"tool": "intent_router", "status": "completed"}
    with (
        patch(
            "app.features.ai.application.playground_routing.plan_playground_turn",
            return_value=None,
        ),
        patch(
            "app.features.ai.application.playground_routing.resolve_customer_routing",
            new_callable=AsyncMock,
            return_value=routing,
        ) as router,
    ):
        result = await route_playground_conversation(
            uuid4(), uuid4(), question="What is the return policy?", transcript=[]
        )
    assert result.completed is False
    assert result.outcome == {"tool": "intent_router", "status": "completed"}
    router.assert_awaited_once_with(
        "What is the return policy?", [], channel="playground", for_generation=True
    )
