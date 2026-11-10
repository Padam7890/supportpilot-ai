"""General conversational query resolution for knowledge retrieval.

Conversation text is context only, never factual evidence or action authorization.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.features.ai.infrastructure.llm_gateway import (
    AIProviderError, generate_completion, is_provider_configured,
)

logger = logging.getLogger(__name__)


class _Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relation: str = "unclear"
    standalone_question: str = Field(default="", max_length=1000)
    confidence: float = Field(default=0, ge=0, le=1)


@dataclass(frozen=True)
class ResolvedQuery:
    question: str
    mode: str


def _history(message: str, transcript: list[dict[str, str]]) -> list[dict[str, str]]:
    turns = transcript[-9:]
    if turns and turns[-1].get("sender") in {"customer", "user"} and turns[-1].get("content", "").strip() == message.strip():
        turns = turns[:-1]
    return [
        {"role": "assistant" if t.get("sender") == "assistant" else "user", "content": t.get("content", "")[:600]}
        for t in turns[-6:] if t.get("sender") in {"assistant", "customer", "user"}
    ]


async def resolve_conversational_query(
    message: str, transcript: list[dict[str, str]],
) -> ResolvedQuery:
    """Resolve short replies and references using bounded recent history.

    Failure returns the original question. Never interprets an action as approved.
    """
    original = message.strip()[:1000]
    history = _history(original, transcript)
    if not history or not is_provider_configured():
        return ResolvedQuery(original, "unchanged")
    # Avoid a model call for clearly standalone questions. Short replies and
    # referential turns are the ambiguous cases that benefit from rewriting.
    if len(original.split()) > 12 and not re.search(r"\b(?:that|those|this|it|them|previous|above)\b", original, re.I):
        return ResolvedQuery(original, "standalone")
    system = (
        "Resolve the latest customer message in context. Return ONLY a JSON object "
        'with keys relation, standalone_question, confidence. relation must be '
        '"follow_up", "new_topic", or "unclear". Rewrite as a standalone QUESTION '
        "preserving the customer's intent and entities. Use previous assistant "
        "questions to interpret short answers, including dates, quantities, names, "
        "and yes/no answers. If the assistant asked for a delivery date and the "
        "customer supplies one, retain the supplied date verbatim and ask what "
        "the verified store policy says about the reporting deadline; do not "
        "assert eligibility or compute deadlines without evidence. Never invent product, policy, "
        "order, or identity facts. Never turn a question into an instruction to "
        "perform a refund, cancellation, payment, or order operation. If unclear, "
        "return the original text and relation unclear."
    )
    payload = {"history": history, "latest_customer_message": original}
    try:
        raw, _, _ = await generate_completion([
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ], max_tokens=260)
        parsed = json.loads(re.sub(r"^\x60\x60\x60(?:json)?\s*|\s*\x60\x60\x60$", "", raw.strip()))
        if not isinstance(parsed, dict):
            return ResolvedQuery(original, "invalid_structure")
        # Small models sometimes omit optional fields or use an alternate
        # query key; normalize the transport shape without inventing meaning.
        if "standalone_question" not in parsed:
            parsed["standalone_question"] = parsed.get("resolved_question", original)
        if "relation" not in parsed:
            parsed["relation"] = "unclear"
        if "confidence" not in parsed:
            parsed["confidence"] = 0
        normalized = {key: parsed[key] for key in ("relation", "standalone_question", "confidence")}
        result = _Resolution.model_validate(normalized)
        if result.relation not in {"follow_up", "new_topic", "unclear"}:
            return ResolvedQuery(original, "invalid_relation")
        if result.relation != "follow_up" or result.confidence < 0.75:
            return ResolvedQuery(original, result.relation)
        rewritten = result.standalone_question.strip()
        # A standalone retrieval query must remain a question, not an executable
        # action or a substitute for tenant-scoped tool authorization.
        if not rewritten.endswith("?") or len(rewritten) > 1000:
            return ResolvedQuery(original, "invalid_question")
        return ResolvedQuery(rewritten, "resolved")
    except (AIProviderError, ValidationError, ValueError, TypeError) as exc:
        logger.info("conversational_query_resolution_fallback reason=%s", type(exc).__name__)
        return ResolvedQuery(original, "model_fallback")
