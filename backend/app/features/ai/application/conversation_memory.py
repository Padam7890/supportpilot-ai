"""Bounded, non-sensitive conversation topic memory derived from recent turns.

This is a read-only projection; never store verification tokens or treat user
messages as proof of identity. Durable persistence is a separate migration.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

_TOPIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("refund", re.compile(r"\b(?:refund|return|exchange|receipt)\b|फिर्ता", re.I)),
    ("delivery", re.compile(r"\b(?:shipping|delivery|courier|shipment)\b|डेलिभरी|ढुवानी", re.I)),
    ("order", re.compile(r"\b(?:order|tracking|track)\b", re.I)),
    ("product", re.compile(r"\b(?:product|stock|size|color|colour|warranty)\b", re.I)),
    ("payment", re.compile(r"\b(?:payment|pay|card|billing)\b|भुक्तानी", re.I)),
)


@dataclass(frozen=True)
class ConversationTopicMemory:
    active_topic: str | None = None
    topic_anchor: str | None = None
    last_customer_message: str | None = None


def derive_topic_memory(
    transcript: list[dict[str, str]], *, max_turns: int = 12
) -> ConversationTopicMemory:
    """Rebuild safe topic context without persisting customer identifiers."""
    latest: str | None = None
    for turn in reversed(transcript[-max_turns:]):
        if turn.get("sender") not in {"customer", "user"}:
            continue
        content = turn.get("content", "").strip()
        if not content:
            continue
        if latest is None:
            latest = content[:240]
        # A named support subject anchors short contextual follow-ups.
        for topic, pattern in _TOPIC_PATTERNS:
            if pattern.search(content):
                return ConversationTopicMemory(
                    active_topic=topic,
                    topic_anchor=content[:240],
                    last_customer_message=latest,
                )
    return ConversationTopicMemory(last_customer_message=latest)
