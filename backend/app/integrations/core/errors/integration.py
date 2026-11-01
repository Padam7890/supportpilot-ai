"""Provider-neutral errors with safe codes and explicit retry semantics."""

from enum import StrEnum


class IntegrationErrorCode(StrEnum):
    PROVIDER_NOT_FOUND = "provider_not_found"
    CONNECTION_NOT_FOUND = "connection_not_found"
    AUTHENTICATION_REQUIRED = "authentication_required"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMITED = "rate_limited"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_PAYLOAD = "invalid_payload"
    UNSUPPORTED_CAPABILITY = "unsupported_capability"
    TRANSIENT_FAILURE = "transient_failure"
    PERMANENT_FAILURE = "permanent_failure"


class IntegrationError(Exception):
    """A safe integration error; never include secrets, PII, or raw payloads."""

    def __init__(
        self,
        code: IntegrationErrorCode,
        *,
        retryable: bool,
        retry_after_seconds: int | None = None,
        provider_code: str | None = None,
    ) -> None:
        if retry_after_seconds is not None and retry_after_seconds < 0:
            raise ValueError("retry_after_seconds cannot be negative")
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
        self.provider_code = provider_code
        super().__init__(code.value)
