"""Structured LLM intent classification with strict validation."""

from __future__ import annotations

import json
import logging
import re
import time

from pydantic import ValidationError

from app.core.config import settings
from app.features.ai.application.conversation_context_builder import build_agent_input
from app.features.ai.application.intent_routing.schemas import (
    DeterministicRouteAssessment,
    RoutingDecision,
)
from app.features.ai.infrastructure.llm_gateway import (
    AIProviderError,
    generate_completion,
    is_provider_configured,
)

logger = logging.getLogger(__name__)

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_SYSTEM = (
    "You classify customer support intent only. Reply with JSON matching the schema. "
    "Do not include tool names, URLs, SQL, or policy claims. "
    "Use general only for standalone conversation or general information unrelated to this store. Never authorize refunds, cancellations, or order access."
)


def _parse_router_json(content: str) -> dict[str, object]:
    stripped = content.strip()
    stripped = _JSON_FENCE.sub("", stripped).strip()
    raw = json.loads(stripped)
    if not isinstance(raw, dict):
        raise TypeError("router output root must be an object")
    return raw


def _build_user_prompt(
    message: str,
    transcript: list[dict[str, str]],
    assessment: DeterministicRouteAssessment,
) -> str:
    context = build_agent_input(message, transcript, channel="widget")
    history = [
        f"{turn.sender}: {turn.content[:320]}"
        for turn in context.history[-6:]
    ]
    candidates = ", ".join(intent.value for intent in assessment.candidate_intents)
    return (
        "Classify the latest customer message.\n"
        f"Deterministic candidates: {candidates}\n"
        f"requires_context={assessment.requires_context}\n"
        f"Recent turns:\n" + ("\n".join(history) if history else "(none)") + "\n"
        f"Latest message:\n{context.message}\n"
        "Return JSON with keys: intents (list of {intent, confidence, requires_knowledge, "
        "requires_tools}), requires_context, should_clarify, reason_code."
    )


async def invoke_llm_intent_router(
    message: str,
    transcript: list[dict[str, str]],
    assessment: DeterministicRouteAssessment,
    *,
    max_attempts: int | None = None,
) -> tuple[RoutingDecision | None, dict[str, int], str | None, str | None]:
    """Return a validated routing decision, token usage, model, and failure code."""
    if not is_provider_configured():
        return None, {}, None, "provider_not_configured"
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _build_user_prompt(message, transcript, assessment)},
    ]
    last_code = "intent_router_failed"
    for attempt in range(max_attempts or settings.ai_intent_router_max_attempts):
        started = time.monotonic()
        try:
            content, usage, model = await generate_completion(
                messages,
                max_tokens=min(256, settings.ai_intent_router_max_tokens),
            )
            decision = RoutingDecision.model_validate(_parse_router_json(content))
            elapsed_ms = round((time.monotonic() - started) * 1000)
            logger.info(
                "intent_llm_router_success elapsed_ms=%d attempt=%d",
                elapsed_ms,
                attempt + 1,
            )
            return decision, usage, model, None
        except (AIProviderError, ValidationError, ValueError, json.JSONDecodeError, TypeError) as exc:
            if isinstance(exc, AIProviderError):
                last_code = exc.code
            else:
                last_code = "intent_router_invalid_response"
            logger.warning(
                "intent_llm_router_attempt_failed code=%s attempt=%d",
                last_code,
                attempt + 1,
            )
    return None, {}, None, last_code
