"""Deterministic safety decisions that must never be delegated to the model."""

from typing import Literal

WidgetReplySuppression = Literal["human_takeover", "teammate_replied", "newer_customer_message"]


def widget_reply_is_superseded(
    *, ai_mode: str, source_is_latest: bool, teammate_replied: bool
) -> WidgetReplySuppression | None:
    """Return a stable suppression reason before any AI response is persisted or sent."""
    if ai_mode != "ai":
        return "human_takeover"
    if teammate_replied:
        return "teammate_replied"
    if not source_is_latest:
        return "newer_customer_message"
    return None
