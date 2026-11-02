"""Safe public/internal AI failure classification."""

import re


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
