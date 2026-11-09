"""First-pass, rule-based customer intent scoring."""

from __future__ import annotations

import re

from app.features.ai.application.conversational_intents import classify_conversational_intent
from app.features.ai.application.intent_routing.schemas import DeterministicRouteAssessment, Intent
from app.features.ai.application.retrieval import is_contextual_follow_up
from app.services import widget_ai


def assess_deterministic_route(
    message: str,
    transcript: list[dict[str, str]],
) -> DeterministicRouteAssessment:
    normalized = message.strip()
    hits: list[tuple[Intent, float, str]] = []
    requires_context = is_contextual_follow_up(message) or any(
        is_contextual_follow_up(item.get("content", "")) for item in transcript[-4:]
    )
    requires_tools = False
    requires_knowledge = False
    risk_level = "low"

    conversational = classify_conversational_intent(message)
    if conversational is not None:
        mapped = Intent.GREETING if conversational.name in {
            "greeting",
            "thanks",
            "goodbye",
            "casual",
        } else Intent.GENERAL
        hits.append((mapped, 0.94, f"conversational_{conversational.name}"))

    if widget_ai.HUMAN_REQUEST.search(normalized):
        hits.append((Intent.HANDOFF, 0.96, "human_handoff_phrase"))

    if widget_ai.CANCELLATION_REQUEST.search(normalized) or widget_ai.widget_request_needs_order_verification(
        normalized
    ):
        hits.append((Intent.ORDER, 0.91, "order_or_tracking"))
        requires_tools = True
        risk_level = "high"

    if widget_ai.REFUND_ACTION.search(normalized) or widget_ai.RETURN_ACTION.search(normalized):
        hits.append((Intent.REFUND, 0.9, "refund_or_return"))
        requires_knowledge = True
        requires_tools = True
        risk_level = "high"

    if widget_ai.PURCHASE_INTENT.search(normalized):
        hits.append((Intent.PRODUCT, 0.88, "purchase_intent"))

    if widget_ai.PRODUCT_QUESTION.search(normalized):
        hits.append((Intent.PRODUCT, 0.78, "product_question"))
        requires_knowledge = True

    if widget_ai.POLICY_QUESTION.search(normalized):
        hits.append((Intent.KNOWLEDGE, 0.8, "policy_question"))
        requires_knowledge = True

    if re.search(r"\b(frustrated|angry|upset|terrible|worst)\b", normalized, re.IGNORECASE):
        hits.append((Intent.COMPLAINT, 0.76, "emotional_language"))
        risk_level = "medium"

    if widget_ai.CLARIFICATION_REQUEST.fullmatch(message.strip()):
        hits.append((Intent.CLARIFICATION, 0.92, "clarification_request"))

    if not hits:
        hits.append((Intent.KNOWLEDGE, 0.55, "default_knowledge"))
        requires_knowledge = True

    unique_intents = {intent for intent, _, _ in hits}
    competing = len(unique_intents) > 1 and not (
        unique_intents <= {Intent.GREETING, Intent.GENERAL}
    )

    primary_intent, primary_score, reason = max(hits, key=lambda item: item[1])
    if competing:
        primary_score = min(primary_score, 0.82)

    if requires_context and primary_score > 0.7:
        primary_score = min(primary_score, 0.84)

    candidates = list(dict.fromkeys(intent for intent, _, _ in sorted(hits, key=lambda i: -i[1])))

    return DeterministicRouteAssessment(
        intent=primary_intent,
        confidence=round(primary_score, 4),
        candidate_intents=candidates[:8],
        requires_context=requires_context,
        requires_tools=requires_tools,
        requires_knowledge=requires_knowledge or primary_intent == Intent.KNOWLEDGE,
        risk_level=risk_level,
        competing=competing,
        reason_code=reason,
    )
