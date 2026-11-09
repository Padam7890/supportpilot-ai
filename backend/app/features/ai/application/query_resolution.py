"""Bounded standalone search query resolution for contextual support turns."""
from __future__ import annotations

import re

_LOCATION = re.compile(r"^(?:for|in|to)\s+(.{2,80}?)\s*[?.!]*$", re.I)


def resolve_retrieval_query(
    message: str,
    *,
    topic_anchor: str | None,
    active_topic: str | None,
    contextual: bool,
    explicit_topic: bool,
) -> str:
    """Rewrite only safe contextual turns; never invent store-specific facts."""
    current = " ".join(message.split())[:1000]
    if not contextual or explicit_topic or not topic_anchor:
        return current
    location = _LOCATION.fullmatch(current)
    if location and active_topic == "delivery":
        return f"delivery shipping fees and availability {location.group(1)}"[:2000]
    if location and active_topic:
        return f"{active_topic} {current}"[:2000]
    return f"{topic_anchor[:240]} {current}"[:2000]
