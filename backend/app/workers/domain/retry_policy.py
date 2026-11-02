"""Shared retry-delay policy for PostgreSQL durable jobs."""

import random


def retry_delay_seconds(
    attempt: int,
    *,
    base_seconds: int = 2,
    cap_seconds: int = 900,
    retry_after_seconds: int | None = None,
    random_value: float | None = None,
) -> int:
    """Return bounded exponential backoff with full jitter or provider retry-after."""
    if attempt < 1 or base_seconds < 1 or cap_seconds < base_seconds:
        raise ValueError("retry policy parameters are outside their valid range")
    if retry_after_seconds is not None:
        return min(cap_seconds, max(1, retry_after_seconds))
    jitter = random.random() if random_value is None else random_value
    if not 0 <= jitter <= 1:
        raise ValueError("random_value must be between zero and one")
    ceiling = min(cap_seconds, base_seconds * 2 ** min(attempt - 1, 16))
    return max(1, round(jitter * ceiling))
