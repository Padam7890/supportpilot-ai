"""Shared customer-turn routing for Playground and Widget (deterministic first)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.features.ai.application.conversational_intents import (
    classify_conversational_intent,
    playground_conversational_reply,
    widget_conversational_reply,
)
from app.features.ai.application.follow_up import infer_assistant_question, resolve_order_support
from app.features.ai.application.retrieval import is_contextual_follow_up
from app.features.ai.application.conversation_understanding import understand_conversation_turn
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


def plan_playground_turn(
    question: str, transcript: list[dict[str, str]] | None = None,
) -> CustomerTurnPlan | None:
    previous = transcript[-1] if transcript else {}
    state = infer_assistant_question(previous.get("content", "")) if previous.get("sender") == "assistant" else None
    order_follow_up = resolve_order_support(" ".join(question.strip().split()), state)
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
    understanding = understand_conversation_turn(question, transcript or [])
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
) -> CustomerTurnPlan:
    understanding = understand_conversation_turn(message, transcript)
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

    sensitive = widget_ai.widget_sensitive_reply(message)
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

    # Knowledge path: follow-ups stay on retrieval (context assembly handles history).
    _ = is_contextual_follow_up(message)
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
