"""Shared widget routing resolution without persistence or delivery side effects."""

from dataclasses import dataclass

from app.features.ai.application.conversation_orchestration import (
    CustomerTurnPlan,
    plan_widget_turn,
)
from app.features.ai.application.intent_routing import (
    apply_routing_to_widget_plan,
    resolve_customer_routing,
)


@dataclass(frozen=True)
class WidgetRouteResult:
    turn: CustomerTurnPlan
    outcome: dict[str, object]
    model_router_invoked: bool


async def resolve_widget_turn(
    message: str,
    transcript: list[dict[str, str]],
    *,
    follow_up_decision: str | None = None,
) -> WidgetRouteResult:
    """Preserve follow-up precedence before optional LLM intent classification."""
    if follow_up_decision is not None:
        return WidgetRouteResult(
            turn=plan_widget_turn(message, transcript),
            outcome={"tool": "widget_follow_up", "status": follow_up_decision},
            model_router_invoked=False,
        )
    routing = await resolve_customer_routing(message, transcript, channel="widget")
    return WidgetRouteResult(
        turn=apply_routing_to_widget_plan(message, transcript, routing),
        outcome=routing.tool_outcome(),
        model_router_invoked=True,
    )
