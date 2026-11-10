"""Widget route coordinator preserves follow-up precedence."""

from unittest.mock import AsyncMock, patch

import pytest

from app.features.ai.application.conversation_orchestration import CustomerTurnPlan
from app.features.ai.application.widget_turn_routing import resolve_widget_turn


@pytest.mark.asyncio
async def test_follow_up_does_not_invoke_llm_router() -> None:
    with patch(
        "app.features.ai.application.widget_turn_routing.resolve_customer_routing",
        new_callable=AsyncMock,
    ) as router, patch(
        "app.features.ai.application.widget_turn_routing.plan_widget_turn",
        return_value=CustomerTurnPlan(route="knowledge"),
    ):
        result = await resolve_widget_turn(
            "What about delivery?", [], follow_up_decision="policy_timing",
        )
    router.assert_not_awaited()
    assert result.turn.route == "knowledge"
    assert result.outcome == {"tool": "widget_follow_up", "status": "policy_timing"}
    assert result.model_router_invoked is False


@pytest.mark.asyncio
async def test_normal_turn_uses_intent_router() -> None:
    routing = AsyncMock()
    routing.tool_outcome = lambda: {"tool": "intent_router", "status": "completed"}
    with patch(
        "app.features.ai.application.widget_turn_routing.resolve_customer_routing",
        new_callable=AsyncMock,
        return_value=routing,
    ) as router, patch(
        "app.features.ai.application.widget_turn_routing.apply_routing_to_widget_plan",
        return_value=CustomerTurnPlan(route="knowledge"),
    ):
        result = await resolve_widget_turn("Where is my order?", [])
    router.assert_awaited_once_with("Where is my order?", [], channel="widget")
    assert result.model_router_invoked is True
    assert result.outcome["tool"] == "intent_router"
