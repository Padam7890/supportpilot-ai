"""Shared widget routing resolution without persistence or delivery side effects."""

from dataclasses import dataclass

from app.features.ai.application.conversation_orchestration import (
    CustomerTurnPlan,
    plan_widget_turn,
)
from app.features.ai.application.intent_routing import (
    CustomerRoutingResolution,
    apply_routing_to_widget_plan,
    resolve_customer_routing,
)


@dataclass(frozen=True)
class WidgetRouteResult:
    turn: CustomerTurnPlan
    outcome: dict[str, object]
    model_router_invoked: bool
    requires_evidence: bool = True


async def resolve_widget_turn(
    message: str,
    transcript: list[dict[str, str]],
    *,
    follow_up_decision: str | None = None,
    allow_model: bool = True,
    routing: CustomerRoutingResolution | None = None,
) -> WidgetRouteResult:
    """Preserve follow-up precedence before optional LLM intent classification."""
    base = plan_widget_turn(message, transcript)
    if follow_up_decision is not None:
        return WidgetRouteResult(
            turn=base,
            outcome={"tool": "widget_follow_up", "status": follow_up_decision},
            model_router_invoked=False,
        )
    if base.route != "knowledge":
        return WidgetRouteResult(base, {"tool": base.tool_name, "status": "completed"}, False)
    if routing is None:
        routing = await resolve_customer_routing(
            message, transcript, channel="widget", for_generation=True, allow_model=allow_model,
        )
    return WidgetRouteResult(
        turn=apply_routing_to_widget_plan(message, transcript, routing, base=base),
        outcome=routing.tool_outcome(),
        model_router_invoked=routing.metrics.llm_router_invocation_count > 0,
        requires_evidence=routing.requires_evidence,
    )
