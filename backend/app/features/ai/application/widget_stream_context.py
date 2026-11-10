"""Provenance for prior widget replies eligible for provisional streaming."""

import json
from uuid import UUID

STREAM_SOURCE_IDS_KEY = "stream_source_ids"
MAX_STREAM_HISTORY_SOURCES = 32


def last_grounded_exchange(
    transcript: list[dict[str, str]],
) -> tuple[list[dict[str, str]], set[str]] | None:
    """Reuse only the latest exchange when its assistant reply was safely streamed."""
    for index in range(len(transcript) - 1, 0, -1):
        turn = transcript[index]
        if turn.get("sender") == "customer":
            continue
        if turn.get("sender") != "assistant" or transcript[index - 1].get("sender") != "customer":
            return None
        try:
            raw_ids = json.loads(turn.get(STREAM_SOURCE_IDS_KEY, "null"))
            if not isinstance(raw_ids, list) or not 1 <= len(raw_ids) <= MAX_STREAM_HISTORY_SOURCES:
                return None
            source_ids = {str(UUID(source_id)) for source_id in raw_ids}
        except (ValueError, TypeError, AttributeError):
            return None
        return transcript[index - 1:], source_ids
    return None
