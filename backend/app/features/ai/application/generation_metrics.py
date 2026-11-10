"""Privacy-safe AI execution metrics.

Usage counts are provider-reported (not inferred from answer length). Costs
are intentionally omitted unless a verified provider price table is supplied.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from time import monotonic
from typing import Any

from app.core.config import settings

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



def normalized_token_totals(usage: Mapping[str, Any] | None) -> dict[str, int | None]:
    """Canonicalize provider counters without counting aliases twice.

    Providers may report input/output or prompt/completion names. Missing
    counters remain unknown; never infer billable usage from response length.
    """
    safe = sanitized_token_usage(usage)
    input_tokens = safe.get("input_tokens", safe.get("prompt_tokens"))
    output_tokens = safe.get("output_tokens", safe.get("completion_tokens"))
    total_tokens = safe.get("total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def configured_model_prices(model_name: str | None) -> tuple[float | None, float | None]:
    """Resolve exact-model pricing; never silently price a different model."""
    if not model_name:
        return None, None
    entry = settings.ai_model_prices.get(model_name)
    if entry is not None:
        return entry.get("input"), entry.get("output")
    if model_name == settings.ai_model:
        return settings.ai_input_cost_per_million, settings.ai_output_cost_per_million
    return None, None


def estimated_generation_cost_usd(
    usage: Mapping[str, Any] | None,
    *,
    input_price_per_million: float | None,
    output_price_per_million: float | None,
) -> str | None:
    """Return a decimal estimate only when both configured prices and counts exist.

    The caller must configure prices for the *actual* provider/model. The
    estimate is not a billing invoice and excludes non-generation charges.
    """
    tokens = normalized_token_totals(usage)
    if (
        input_price_per_million is None or output_price_per_million is None
        or tokens["input_tokens"] is None or tokens["output_tokens"] is None
    ):
        return None
    try:
        input_price = Decimal(str(input_price_per_million))
        output_price = Decimal(str(output_price_per_million))
        if not input_price.is_finite() or not output_price.is_finite():
            return None
        if input_price < 0 or output_price < 0:
            return None
        amount = (
            Decimal(tokens["input_tokens"]) * input_price
            + Decimal(tokens["output_tokens"]) * output_price
        ) / Decimal(1_000_000)
        return str(amount.quantize(Decimal("0.00000001")))
    except (InvalidOperation, ValueError):
        return None


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
            "usage": normalized_token_totals(usage),
            "cost_usd": None,  # Actual provider bill is not known.
            "estimated_cost_usd": estimated_generation_cost_usd(
                usage,
                input_price_per_million=configured_model_prices(model_name)[0],
                output_price_per_million=configured_model_prices(model_name)[1],
            ),
        }, sort_keys=True),
    )
