"""Privacy-safe AI execution metrics.

Usage counts are provider-reported (not inferred from answer length). Costs
are intentionally omitted unless a verified provider price table is supplied.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from time import monotonic
from typing import Any

logger = logging.getLogger(__name__)
_MAX_TOKENS = 10_000_000


def sanitized_token_usage(usage: Mapping[str, Any] | None) -> dict[str, int]:
    """Accept only known, bounded token counters. Never log prompts or responses."""
    if not isinstance(usage, Mapping):
        return {}
    result: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens",
                "prompt_tokens", "completion_tokens"):
        value = usage.get(key)
        if type(value) is int and 0 <= value <= _MAX_TOKENS:
            result[key] = value
    return result


def log_generation_metrics(
    *, execution_id: str, execution_kind: str, model_name: str | None,
    started_monotonic: float, usage: Mapping[str, Any] | None,
    streamed: bool, correlation_id: str | None = None,
) -> None:
    """Emit one bounded JSON record for a completed model generation."""
    elapsed_ms = max(0, round((monotonic() - started_monotonic) * 1000))
    logger.info(
        "ai_generation_metrics %s",
        json.dumps({
            "event": "ai_generation_completed",
            "execution_id": execution_id,
            "correlation_id": correlation_id,
            "execution_kind": execution_kind,
            "model_name": (model_name or "unknown")[:120],
            "duration_ms": elapsed_ms,
            "streamed": streamed,
            "usage": sanitized_token_usage(usage),
            "cost_usd": None,  # Unknown until verified per-model pricing is configured.
        }, sort_keys=True),
    )
