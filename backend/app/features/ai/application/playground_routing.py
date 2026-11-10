"""Playground conversation routing, distinct from storefront action execution."""

from dataclasses import dataclass
from uuid import UUID

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.catalog_discovery import (
    list_verified_products,
    render_product_listing,
    resolve_catalog_connection,
)
from app.features.ai.application.conversation_orchestration import plan_playground_turn
from app.features.ai.application.execution_lifecycle import finish_deterministic_ai_execution
from app.features.ai.application.intent_routing import (
    CustomerRoutingResolution,
    resolve_customer_routing,
)
from app.features.ai.application.policy_follow_up import FollowUpInterpretation


@dataclass(frozen=True)
class PlaygroundRoutingResult:
    completed: bool
    outcome: dict[str, object] | None = None
    requires_evidence: bool = True
    interpretation: FollowUpInterpretation | None = None


async def route_playground_conversation(
    organization_id: UUID,
    execution_id: UUID,
    *,
    question: str,
    transcript: list[dict[str, str]] | None,
    routing: CustomerRoutingResolution | None = None,
) -> PlaygroundRoutingResult:
    """Finish deterministic preview turns; classify other turns for retrieval."""
    if routing is None:
        routing = await resolve_customer_routing(
            question, transcript or [], channel="playground", for_generation=True,
        )
    interpretation = routing.llm.follow_up if routing.llm else None
    plan = plan_playground_turn(question, transcript, interpretation=interpretation)
    if plan is not None and plan.route == "inventory":
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            connection_id = await resolve_catalog_connection(
                db, organization_id, bound_connection_id=None,
            )
            products = (
                await list_verified_products(db, organization_id, connection_id=connection_id)
                if connection_id is not None else []
            )
        await finish_deterministic_ai_execution(
            organization_id, execution_id,
            draft=(
                render_product_listing(products) if connection_id is not None
                else "Please select a connected store before browsing products."
            ),
            safe_summary="Playground catalog preview from an unambiguous connected integration.",
            tool_name="catalog_discovery",
            result_count=len(products),
        )
        return PlaygroundRoutingResult(completed=True)
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
    return PlaygroundRoutingResult(
        completed=False, outcome=routing.tool_outcome(), requires_evidence=routing.requires_evidence,
        interpretation=routing.llm.follow_up if routing.llm else None,
    )
