"""Privacy-safe intent router observability."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class IntentRouterMetrics:
    deterministic_route_count: int = 0
    llm_router_invocation_count: int = 0
    llm_router_failure_count: int = 0
    ambiguous_intent_count: int = 0
    multi_intent_count: int = 0
    routing_latency_ms: int = 0
    router_prompt_tokens: int = 0
    router_completion_tokens: int = 0
    estimated_router_cost_usd: float | None = None

    def to_log_fields(self) -> dict[str, object]:
        return {
            "deterministic_route_count": self.deterministic_route_count,
            "llm_router_invocation_count": self.llm_router_invocation_count,
            "llm_router_failure_count": self.llm_router_failure_count,
            "ambiguous_intent_count": self.ambiguous_intent_count,
            "multi_intent_count": self.multi_intent_count,
            "routing_latency_ms": self.routing_latency_ms,
            "router_token_usage": {
                "prompt_tokens": self.router_prompt_tokens,
                "completion_tokens": self.router_completion_tokens,
            },
            "estimated_router_cost_usd": self.estimated_router_cost_usd,
        }


def estimate_router_cost_usd(*, prompt_tokens: int, completion_tokens: int) -> float | None:
    if settings.ai_input_cost_per_million is None or settings.ai_output_cost_per_million is None:
        return None
    prompt_cost = prompt_tokens * settings.ai_input_cost_per_million / 1_000_000
    completion_cost = completion_tokens * settings.ai_output_cost_per_million / 1_000_000
    return round(prompt_cost + completion_cost, 6)


@dataclass
class _AggregateCounters:
    messages: int = 0
    llm_invocations: int = 0

_aggregate = _AggregateCounters()


def record_aggregate(*, llm_invoked: bool) -> None:
    _aggregate.messages += 1
    if llm_invoked:
        _aggregate.llm_invocations += 1


def reset_aggregate_for_tests() -> None:
    _aggregate.messages = 0
    _aggregate.llm_invocations = 0


def aggregate_snapshot() -> dict[str, float]:
    if _aggregate.messages == 0:
        return {"llm_invocation_percent": 0.0, "sample_size": 0.0}
    return {
        "llm_invocation_percent": round(100 * _aggregate.llm_invocations / _aggregate.messages, 4),
        "sample_size": float(_aggregate.messages),
    }


def log_intent_router_event(metrics: IntentRouterMetrics, *, mode: str, reason_code: str) -> None:
    logger.info(
        "intent_router_event %s",
        {
            "mode": mode,
            "reason_code": reason_code,
            **metrics.to_log_fields(),
            **aggregate_snapshot(),
        },
    )
