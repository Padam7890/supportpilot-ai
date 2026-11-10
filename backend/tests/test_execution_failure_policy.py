"""Retry and failure decisions remain deterministic and independent of persistence."""

import pytest

from app.features.ai.application.execution_failure_policy import (
    assess_execution_failure,
    decide_execution_retry,
)
from app.features.ai.infrastructure.llm_gateway import AIProviderError


def test_provider_http_failure_preserves_safe_status() -> None:
    result = assess_execution_failure(
        AIProviderError("provider_http_429", "rate limited", http_status=429),
        "provider_generation",
    )
    assert result.code == "provider_http_429"
    assert result.http_status == 429


def test_unknown_retrieval_failure_uses_stage_specific_code() -> None:
    result = assess_execution_failure(RuntimeError("secret"), "knowledge_retrieval")
    assert result.code == "knowledge_retrieval_failed"


@pytest.mark.parametrize(
    ("retryable", "attempt", "maximum", "kind", "reason", "fallback"),
    [
        (True, 1, 3, "widget_reply", "retry_scheduled", False),
        (True, 3, 3, "widget_reply", "retry_exhausted", True),
        (False, 1, 3, "widget_reply", "not_retryable", True),
        (True, 3, 3, "playground", "retry_exhausted", False),
        (False, 1, 3, "playground", "not_retryable", False),
    ],
)
def test_retry_policy(retryable, attempt, maximum, kind, reason, fallback) -> None:
    decision = decide_execution_retry(
        retryable=retryable, attempt_count=attempt, max_attempts=maximum,
        execution_kind=kind,
    )
    assert decision.reason == reason
    assert decision.widget_needs_fallback is fallback
    assert (decision.delay_seconds is None) is decision.exhausted


@pytest.mark.parametrize(("attempt", "maximum"), [(0, 3), (1, 0), (-1, 3)])
def test_retry_policy_rejects_invalid_attempts(attempt, maximum) -> None:
    with pytest.raises(ValueError):
        decide_execution_retry(
            retryable=True, attempt_count=attempt,
            max_attempts=maximum, execution_kind="widget_reply",
        )
