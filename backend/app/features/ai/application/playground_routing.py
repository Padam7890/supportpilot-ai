"""Playground conversation routing, distinct from storefront action execution."""

from dataclasses import dataclass
from uuid import UUID

from app.features.ai.application.conversation_orchestration import plan_playground_turn
from app.features.ai.application.execution_lifecycle import finish_deterministic_ai_execution
from app.features.ai.application.intent_routing import resolve_customer_routing


@dataclass(frozen=True)
class PlaygroundRoutingResult:
    completed: bool
    outcome: dict[str, object] | None = None


async def route_playground_conversation(
    organization_id: UUID,
    execution_id: UUID,
    *,
    question: str,
    transcript: list[dict[str, str]] | None,
) -> PlaygroundRoutingResult:
    """Finish deterministic preview turns; classify other turns for retrieval."""
    plan = plan_playground_turn(question, transcript)
    if plan is not None:
        await finish_deterministic_ai_execution(
            organization_id,
            execution_id,
            draft=plan.draft or "",
            safe_summary=plan.safe_summary or "",
            tool_name=plan.tool_name,
            result_count=0,
        )
        return PlaygroundRoutingResult(completed=True)
    routing = await resolve_customer_routing(
        question, transcript or [], channel="playground"
    )
    return PlaygroundRoutingResult(completed=False, outcome=routing.tool_outcome())
