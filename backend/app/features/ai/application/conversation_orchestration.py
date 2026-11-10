"""Shared customer-turn routing for Playground and Widget (deterministic first)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.features.ai.application.catalog_discovery import is_catalog_discovery_request
from app.features.ai.application.conversation_understanding import understand_conversation_turn
from app.features.ai.application.policy_follow_up import FollowUpInterpretation
from app.features.ai.application.conversational_intents import (
    classify_conversational_intent,
    playground_conversational_reply,
    widget_conversational_reply,
)
from app.features.ai.application.follow_up import resolve_order_support
from app.features.ai.application.retrieval import is_contextual_follow_up
from app.services import widget_ai

Route = Literal[
    "direct",
    "purchase",
    "sensitive",
    "clarification",
    "shopping",
    "knowledge",
    "inventory",
]


@dataclass(frozen=True)
class CustomerTurnPlan:
    route: Route
    draft: str | None = None
    safe_summary: str | None = None
    intent: str | None = None
    reply_status: str = "sent"
    tool_name: str = "conversation_intent"



def _negated_action_plan() -> CustomerTurnPlan:
    """A negative instruction never starts or confirms a commerce operation."""
    return CustomerTurnPlan(
        route="direct",
        draft=(
            "Understood. I won't start a cancellation, return, or refund request "
            "from this message. If a request was already submitted, please contact "
            "the store team to check its status."
        ),
        safe_summary="The shopper negated an action; no commerce operation was initiated.",
        intent="negated_action",
        tool_name="conversation_negated_action",
    )


def plan_playground_turn(
    question: str, transcript: list[dict[str, str]] | None = None,
    *, interpretation: FollowUpInterpretation | None = None,
) -> CustomerTurnPlan | None:
    understanding = understand_conversation_turn(
        question, transcript or [], interpretation=interpretation,
    )
    if understanding.negated_action:
        return _negated_action_plan()
    order_follow_up = resolve_order_support(" ".join(question.strip().split()))
    if order_follow_up and order_follow_up.draft:
        return CustomerTurnPlan(
            route="direct",
            draft=(
                "The storefront would pass this conversation to the store team. "
                "This Playground preview does not contact them."
                if order_follow_up.handoff else order_follow_up.draft
            ),
            safe_summary="Previewed a secure order support next step.",
            intent="order",
            tool_name="playground_order_follow_up",
        )
    if is_catalog_discovery_request(question):
        return CustomerTurnPlan(route="inventory", intent="catalog_list", tool_name="catalog_discovery")
    if understanding.needs_clarification:
        return CustomerTurnPlan(route="clarification", draft="Could you clarify which product, order, or policy you mean?", intent="clarification")
    conversational = playground_conversational_reply(question)
    if conversational is not None:
        draft, intent = conversational
        return CustomerTurnPlan(
            route="direct",
            draft=draft,
            safe_summary=(
                f"A deterministic {intent} response was returned without document retrieval or a model call."
            ),
            intent=intent,
            tool_name="playground_conversation_intent",
        )
    return None


def plan_widget_turn(
    message: str,
    transcript: list[dict[str, str]],
    *, interpretation: FollowUpInterpretation | None = None,
) -> CustomerTurnPlan:
    understanding = understand_conversation_turn(
        message, transcript, interpretation=interpretation,
    )
    if understanding.negated_action:
        return _negated_action_plan()
    if is_catalog_discovery_request(message):
        return CustomerTurnPlan(route="inventory", intent="catalog_list", tool_name="catalog_discovery")
    if understanding.needs_clarification:
        return CustomerTurnPlan(route="clarification", draft="Could you tell me which product, order, or policy you're referring to?", intent="clarification", tool_name="widget_context_clarification")
    conversational = widget_conversational_reply(message)
    if conversational is not None:
        draft, intent = conversational
        return CustomerTurnPlan(
            route="direct",
            draft=draft,
            safe_summary="A conversational reply was prepared without using private customer or order data.",
            intent=intent,
            tool_name="widget_conversation_intent",
        )

    purchase = widget_ai.widget_purchase_reply(message)
    if purchase is not None:
        return CustomerTurnPlan(
            route="purchase",
            draft=purchase,
            safe_summary="The shopper asked to place an order and was directed to the merchant’s checkout; no purchase was created.",
            intent="purchase",
            tool_name="widget_purchase_intent",
        )

    # A question about a sensitive subject is not itself a request to execute
    # a sensitive operation. Let informational questions use grounded retrieval.
    # This is a speech-act guard, not a list of policy-specific phrases.
    informational_question = bool(re.match(
        r"^\\s*(?:what|why|when|where|which|who|how|is|are|does|do|did|"
        r"should|would|could|can)\\b", message, re.IGNORECASE,
    )) and not bool(re.match(
        r"^\\s*(?:(?:can|could|would|will)\\s+you\\s+|please\\s+)",
        message, re.IGNORECASE,
    ))
    sensitive = None if informational_question else widget_ai.widget_sensitive_reply(message)
    if sensitive is not None:
        draft, safe_summary = sensitive
        return CustomerTurnPlan(
            route="sensitive",
            draft=draft,
            safe_summary=safe_summary,
            intent="sensitive",
            reply_status="escalated",
            tool_name="widget_sensitive_intent",
        )

    clarification = widget_ai.widget_clarification_reply(message, transcript)
    if clarification is not None:
        return CustomerTurnPlan(
            route="clarification",
            draft=clarification,
            safe_summary="A deterministic clarification explained the active support workflow without a model call.",
            intent="clarification",
            tool_name="widget_clarification_intent",
        )

    # Follow-ups stay on retrieval; context assembly resolves the history.
    return CustomerTurnPlan(route="knowledge")


def playground_missing_knowledge_reply(question: str) -> str:
    """Helpful playground response when retrieval is empty — not a provider failure."""
    if is_contextual_follow_up(question):
        return (
            "I’m not sure which topic you mean yet. Could you repeat your question with a few more details "
            "so I can search this bot’s assigned sources?"
        )
    conversational = classify_conversational_intent(question)
    if conversational is not None:
        return conversational.playground_reply
    return (
        "I couldn't find relevant information in this AI bot's assigned knowledge sources, "
        "so I can't answer accurately yet. Add or assign a source that covers this question."
    )
