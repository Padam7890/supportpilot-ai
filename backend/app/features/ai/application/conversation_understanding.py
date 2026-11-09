"""Typed, deterministic understanding of a customer turn and its local context."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.features.ai.application.follow_up import PendingQuestion, pending_from_assistant
from app.features.ai.application.retrieval import build_retrieval_terms, is_contextual_follow_up


@dataclass(frozen=True)
class ConversationUnderstanding:
    """A bounded view of the latest turn; transcript text is never trusted evidence."""

    message: str
    contextual_follow_up: bool
    topic_switch: bool
    multi_intent: bool
    retrieval_query: str
    pending_state: PendingQuestion | None
    language: Literal["en", "ne", "mixed"] = "en"
    candidate_intents: tuple[str, ...] = ()
    needs_clarification: bool = False


def understand_conversation_turn(
    message: str,
    transcript: list[dict[str, str]],
    *,
    agent_id=None,
    now=None,
) -> ConversationUnderstanding:
    """Resolve only context-dependent short turns; explicit new topics stand alone."""
    from datetime import UTC, datetime

    from app.features.ai.application.intent_routing.deterministic import assess_deterministic_route

    normalized = " ".join(message.split())
    prior_turns = transcript
    if (
        prior_turns
        and prior_turns[-1].get("sender") in {"customer", "user"}
        and prior_turns[-1].get("content", "").strip() == normalized
    ):
        prior_turns = prior_turns[:-1]
    recent_customer_turns = [
        item.get("content", "").strip()
        for item in reversed(prior_turns[-12:])
        if item.get("sender") in {"customer", "user"}
        and item.get("content", "").strip()
    ]
    # Prefer the latest explicit subject over acknowledgements and pronouns.
    previous_customer = next(
        (turn for turn in recent_customer_turns if _has_explicit_topic(turn)),
        recent_customer_turns[0] if recent_customer_turns else "",
    )
    contextual = is_contextual_follow_up(normalized) or _is_short_prepositional_follow_up(normalized)
    # A follow-up that names its own subject ("what about shipping?") already
    # forms a usable query. Do not blend an earlier, unrelated question into it.
    topic_switch = _has_explicit_topic(normalized)
    query_parts = (
        [previous_customer[-240:], normalized]
        if contextual and not topic_switch and previous_customer
        else [normalized]
    )
    recent_intents = assess_deterministic_route(normalized, [])
    unique_intents = set(recent_intents.candidate_intents)
    multi_intent = len(unique_intents) > 1 and recent_intents.competing
    pending = None
    if prior_turns and agent_id is not None:
        pending = pending_from_assistant(
            prior_turns[-1], agent_id, now or datetime.now(UTC)
        )
    language = _detect_language(normalized)
    return ConversationUnderstanding(
        message=normalized,
        contextual_follow_up=contextual,
        topic_switch=topic_switch,
        multi_intent=multi_intent,
        retrieval_query=" ".join(query_parts)[:2000],
        pending_state=pending,
        language=language,
        candidate_intents=tuple(intent.value for intent in recent_intents.candidate_intents),
        needs_clarification=bool(contextual and not topic_switch and not previous_customer),
    )


_TOPIC_TERMS = re.compile(
    r"\b(?:refund|return|exchange|shipping|delivery|ship|track|tracking|order|"
    r"product|phone|laptop|recommend|compare|payment|card|warranty|hours|"
    r"cancel|cancellation|contact|store|policy|price|stock|available)\b|"
    r"(?:फिर्ता|ढुवानी|डेलिभरी|भुक्तानी)",
    re.IGNORECASE,
)


def _has_explicit_topic(message: str) -> bool:
    """Only explicit subject terms sever the active retrieval topic."""
    return bool(_TOPIC_TERMS.search(message)) and bool(build_retrieval_terms(message))

def _is_short_prepositional_follow_up(message: str) -> bool:
    """Resolve short 'for Kathmandu?' or 'in Pokhara?' questions against the active topic."""
    tokens = message.strip().casefold().rstrip("?.!").split()
    return 2 <= len(tokens) <= 4 and tokens[0] in {"for", "in", "to"}

_ROMANIZED_NEPALI = frozenset({
    "mero", "malai", "tapai", "tapaiiko", "cha", "chha", "kati",
    "kasari", "kahile", "kina", "kaha", "kata", "garna", "garnu",
    "paisa", "saman", "yo", "tyo", "ani", "huncha", "hunchha",
})


def _detect_language(message: str) -> Literal["en", "ne", "mixed"]:
    """Cheap script/lexical signal; not a full language detector."""
    devanagari = bool(re.search(r"[\\u0900-\\u097f]", message))
    words = re.findall(r"[a-z]+", message.casefold())
    romanized = any(word in _ROMANIZED_NEPALI for word in words)
    english = any(word not in _ROMANIZED_NEPALI for word in words)
    if devanagari and english or romanized and english:
        return "mixed"
    if devanagari or romanized:
        return "ne"
    return "en"
