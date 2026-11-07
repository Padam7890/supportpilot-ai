"""Request correlation helpers that carry safe identifiers into durable work."""

from contextvars import ContextVar
from uuid import uuid4

_correlation_id: ContextVar[str | None] = ContextVar("supportpilot_correlation_id", default=None)


def current_correlation_id() -> str:
    return _correlation_id.get() or str(uuid4())


def set_correlation_id(value: str):
    return _correlation_id.set(value)


def reset_correlation_id(token) -> None:
    _correlation_id.reset(token)
