"""Resolve customer routing: deterministic first, optional structured LLM."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.features.ai.application.conversation_orchestration import (
    CustomerTurnPlan,
    plan_widget_turn,
)
from app.features.ai.application.intent_routing.deterministic import assess_deterministic_route
from app.features.ai.application.intent_routing.llm_router import invoke_llm_intent_router
from app.features.ai.application.intent_routing.metrics import (
    IntentRouterMetrics,
    estimate_router_cost_usd,
    log_intent_router_event,
    record_aggregate,
)
from app.features.ai.application.intent_routing.policy import should_invoke_llm_router
from app.features.ai.application.intent_routing.schemas import Intent, RoutingDecision, DeterministicRouteAssessment
from app.core.config import settings
from app.services import widget_ai

CLARIFICATION_PROMPT = (
    "I want to make sure I help with the right thing. Could you share a bit more detail "
    "about what you need—for example your order, a product, or a store policy?"
)


@dataclass
class CustomerRoutingResolution:
    deterministic: DeterministicRouteAssessment
    llm: RoutingDecision | None = None
    mode: str = "deterministic"
    failure_code: str | None = None
    clarify: bool = False
    multi_intent: bool = False
    metrics: IntentRouterMetrics = field(default_factory=IntentRouterMetrics)

    def tool_outcome(self) -> dict[str, object]:
        det = self.deterministic
        return {
            "tool": "intent_router",
            "status": "completed" if not self.failure_code else "degraded",
            "mode": self.mode,
            "primary_intent": det.intent.value,
            "deterministic_confidence": det.confidence,
            "candidate_intents": [intent.value for intent in det.candidate_intents],
            "requires_context": det.requires_context,
            "requires_tools": det.requires_tools,
            "requires_knowledge": det.requires_knowledge,
            "risk_level": det.risk_level,
            "llm_failure_code": self.failure_code,
            "multi_intent": self.multi_intent,
            "should_clarify": self.clarify,
            "metrics": self.metrics.to_log_fields(),
        }


async def resolve_customer_routing(
    message: str,
    transcript: list[dict[str, str]],
    *,
    channel: str,
) -> CustomerRoutingResolution:
    started = time.monotonic()
    assessment = assess_deterministic_route(message, transcript)
    metrics = IntentRouterMetrics(deterministic_route_count=1)
    if assessment.competing or assessment.confidence < 0.75:
        metrics.ambiguous_intent_count = 1

    resolution = CustomerRoutingResolution(
        deterministic=assessment, mode="deterministic",
        multi_intent=assessment.competing,
    )
    if assessment.competing:
        metrics.multi_intent_count = 1
    invoke = should_invoke_llm_router(assessment, message)
    llm_invoked = False

    if invoke:
        llm_invoked = True
        metrics.llm_router_invocation_count = 1
        decision, usage, router_model, failure = await invoke_llm_intent_router(message, transcript, assessment)
        if decision is not None and not assessment.requires_tools and any(
            item.requires_tools or item.intent in {Intent.ORDER, Intent.REFUND}
            for item in decision.intents
        ) and assessment.intent not in {Intent.ORDER, Intent.REFUND}:
            # Model-suggested commerce actions cannot upgrade a deterministic
            # non-commerce request into an actionable order/refund workflow.
            decision = None
            failure = "unsafe_llm_commerce_escalation"
        if decision is not None:
            resolution.mode = "llm"
            resolution.llm = decision
            resolution.multi_intent = len(decision.intents) > 1 or assessment.competing
            resolution.clarify = decision.should_clarify or any(
                item.confidence < settings.ai_intent_router_low_confidence for item in decision.intents
            )
            if resolution.multi_intent:
                metrics.multi_intent_count = 1
            metrics.router_prompt_tokens = usage.get("prompt_tokens", 0)
            metrics.router_completion_tokens = usage.get("completion_tokens", 0)
            metrics.estimated_router_cost_usd = estimate_router_cost_usd(
                prompt_tokens=metrics.router_prompt_tokens,
                completion_tokens=metrics.router_completion_tokens,
                model_name=router_model,
            )
        else:
            metrics.llm_router_failure_count = 1
            resolution.failure_code = failure
            resolution.clarify = (
                assessment.confidence < settings.ai_intent_router_low_confidence
                or assessment.competing and assessment.risk_level != "high"
            )
            resolution.mode = "deterministic_fallback"

    metrics.routing_latency_ms = round((time.monotonic() - started) * 1000)
    resolution.metrics = metrics
    record_aggregate(llm_invoked=llm_invoked)
    log_intent_router_event(metrics, mode=resolution.mode, reason_code=assessment.reason_code)
    _ = channel
    return resolution


def apply_routing_to_widget_plan(
    message: str,
    transcript: list[dict[str, str]],
    resolution: CustomerRoutingResolution,
) -> CustomerTurnPlan:
    base = plan_widget_turn(message, transcript)
    if base.route != "knowledge":
        return base

    intent_set = {item.intent for item in resolution.llm.intents} if resolution.llm else set()
    if resolution.llm is None:
        intent_set = set(resolution.deterministic.candidate_intents)

    if Intent.ORDER in intent_set and resolution.deterministic.requires_tools:
        sensitive = widget_ai.widget_sensitive_reply(message)
        if sensitive is not None:
            draft, safe_summary = sensitive
            return CustomerTurnPlan(
                route="sensitive",
                draft=draft,
                safe_summary=safe_summary,
                intent="multi_intent_order",
                reply_status="escalated",
                tool_name="intent_router_sensitive",
            )

    should_clarify = resolution.clarify
    if resolution.llm is not None:
        should_clarify = should_clarify or resolution.llm.should_clarify
    if should_clarify and (
        resolution.llm is not None
        or resolution.deterministic.confidence < settings.ai_intent_router_low_confidence
    ):
        return CustomerTurnPlan(
            route="clarification",
            draft=CLARIFICATION_PROMPT,
            safe_summary="Intent was ambiguous; a clarification was returned without inventing store facts.",
            intent="clarification",
            tool_name="intent_router_clarification",
        )
    return base
