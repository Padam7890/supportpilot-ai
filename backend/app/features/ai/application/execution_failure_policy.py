"""Pure failure classification and retry decisions for durable AI jobs.

This policy never reads database state or exposes exception messages to customers.
"""

import re
from dataclasses import dataclass

from app.features.ai.domain.failure_codes import (
    is_retryable_ai_failure,
    safe_ai_failure_code,
)
from app.features.ai.infrastructure.llm_gateway import AIProviderError
from app.workers.domain.retry_policy import retry_delay_seconds


@dataclass(frozen=True)
class FailureAssessment:
    code: str
    retryable: bool
    http_status: int | None
    provider_reason: str | None


@dataclass(frozen=True)
class RetryDecision:
    exhausted: bool
    reason: str
    delay_seconds: int | None
    widget_needs_fallback: bool


def assess_execution_failure(exc: Exception, stage: str) -> FailureAssessment:
    code = safe_ai_failure_code(exc)
    if stage == "knowledge_retrieval" and code == "ai_execution_failed":
        code = "knowledge_retrieval_failed"
    status_match = re.fullmatch(r"provider_http_(\d{3})", code)
    http_status = (
        exc.http_status if isinstance(exc, AIProviderError) and exc.http_status is not None
        else int(status_match.group(1)) if status_match else None
    )
    return FailureAssessment(
        code=code,
        retryable=is_retryable_ai_failure(exc),
        http_status=http_status,
        provider_reason=exc.provider_reason if isinstance(exc, AIProviderError) else None,
    )


def decide_execution_retry(
    *,
    retryable: bool,
    attempt_count: int,
    max_attempts: int,
    execution_kind: str,
) -> RetryDecision:
    if attempt_count < 1 or max_attempts < 1:
        raise ValueError("Attempt counts must be positive")
    exhausted = not retryable or attempt_count >= max_attempts
    return RetryDecision(
        exhausted=exhausted,
        reason="retry_scheduled" if not exhausted else (
            "retry_exhausted" if retryable else "not_retryable"
        ),
        delay_seconds=(
            None if exhausted else retry_delay_seconds(attempt_count, base_seconds=5, cap_seconds=60)
        ),
        widget_needs_fallback=exhausted and execution_kind == "widget_reply",
    )
