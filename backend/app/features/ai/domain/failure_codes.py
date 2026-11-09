"""Safe public/internal AI failure classification."""

import re

from sqlalchemy.exc import DBAPIError


def safe_ai_failure_code(exc: Exception) -> str:
    """Classify known failures without persisting exception contents or secrets."""
    safe_code = getattr(exc, "code", None)
    if isinstance(safe_code, str) and re.fullmatch(r"[a-z0-9_]{1,80}", safe_code):
        return safe_code
    message = str(exc)
    provider_status = re.fullmatch(r"AI provider returned HTTP (\d{3})", message)
    if provider_status:
        return f"provider_http_{provider_status.group(1)}"
    if message == "AI provider is not configured":
        return "provider_not_configured"
    if message == "AI provider URL must use HTTPS outside local development":
        return "provider_url_invalid"
    if message == "AI provider returned an empty draft":
        return "provider_empty_response"
    return "ai_execution_failed"


def is_retryable_ai_failure(exc: Exception) -> bool:
    """Retry only known transient provider and invalidated database connections."""
    if getattr(exc, "provider_reason", None) in {
        "insufficient_quota", "credit_balance_exhausted", "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded", "organization_usage_limit_exceeded",
    }:
        return False
    code = safe_ai_failure_code(exc)
    if code in {"provider_timeout", "provider_unreachable", "workflow_timeout"}:
        return True
    provider_status = re.fullmatch(r"provider_http_(\d{3})", code)
    if provider_status:
        status = int(provider_status.group(1))
        return status in {408, 425, 429} or 500 <= status <= 599
    return isinstance(exc, DBAPIError) and bool(exc.connection_invalidated)
