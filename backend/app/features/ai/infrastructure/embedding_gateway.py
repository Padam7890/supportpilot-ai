"""Validated, server-side OpenAI-compatible embedding gateway."""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import settings
from app.workers.domain.retry_policy import retry_delay_seconds


@dataclass(frozen=True)
class EmbeddingVector:
    values: list[float]
    model: str
    dimensions: int


class EmbeddingProviderError(RuntimeError):
    """Provider failure with a safe code suitable for job state and logs."""

    def __init__(self, code: str, *, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


def effective_embedding_base_url() -> str | None:
    explicit = (settings.ai_embedding_base_url or "").strip().rstrip("/")
    if explicit:
        return explicit
    shared = (settings.ai_provider_base_url or "").strip().rstrip("/")
    return shared or None


def effective_embedding_api_key() -> str | None:
    if settings.ai_embedding_api_key is not None:
        return settings.ai_embedding_api_key.get_secret_value()
    if settings.ai_provider_api_key is not None:
        return settings.ai_provider_api_key.get_secret_value()
    return None


def is_embedding_provider_configured() -> bool:
    return bool(effective_embedding_base_url() and settings.ai_embedding_model)


def _validate_provider_url(base_url: str) -> None:
    parsed = urlsplit(base_url)
    local_http_host = parsed.scheme == "http" and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if (
        (parsed.scheme != "https" and not local_http_host)
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise EmbeddingProviderError("embedding_provider_url_invalid", retryable=False)


async def _embed_texts_once(
    texts: list[str],
    *,
    model: str,
    dimensions: int,
    base_url: str,
    api_key: str | None,
    timeout_seconds: int,
) -> list[EmbeddingVector]:
    import httpx

    if not texts or len(texts) > settings.ai_embedding_batch_size:
        raise ValueError("embedding batch size is outside configured bounds")
    if any(not isinstance(text, str) or not text.strip() or len(text) > 20_000 for text in texts):
        raise ValueError("embedding input is invalid")
    _validate_provider_url(base_url)

    headers = {"content-type": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    payload: dict[str, object] = {"model": model, "input": texts, "dimensions": dimensions}
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(f"{base_url}/embeddings", headers=headers, json=payload)
    except httpx.TimeoutException as exc:
        raise EmbeddingProviderError("embedding_provider_timeout", retryable=True) from exc
    except httpx.RequestError as exc:
        raise EmbeddingProviderError("embedding_provider_unreachable", retryable=True) from exc

    if response.status_code == 429 or response.status_code >= 500:
        raise EmbeddingProviderError(
            f"embedding_provider_http_{response.status_code}", retryable=True
        )
    if response.status_code >= 400:
        raise EmbeddingProviderError(
            f"embedding_provider_http_{response.status_code}", retryable=False
        )
    try:
        data = response.json().get("data")
        if not isinstance(data, list) or len(data) != len(texts):
            raise ValueError("unexpected embedding count")
        indexed: list[tuple[int, list[float]]] = []
        for fallback_index, item in enumerate(data):
            if not isinstance(item, dict):
                raise TypeError("unexpected embedding item")
            index = item.get("index", fallback_index)
            raw_values = item.get("embedding")
            if (
                isinstance(index, bool)
                or not isinstance(index, int)
                or not isinstance(raw_values, list)
            ):
                raise TypeError("unexpected embedding shape")
            if len(raw_values) != dimensions:
                raise ValueError("embedding dimension mismatch")
            values = [float(value) for value in raw_values]
            if any(not math.isfinite(value) for value in values):
                raise ValueError("non-finite embedding value")
            indexed.append((index, values))
        indexed.sort(key=lambda row: row[0])
        if [index for index, _ in indexed] != list(range(len(texts))):
            raise ValueError("embedding indices are incomplete")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise EmbeddingProviderError(
            "embedding_provider_invalid_response", retryable=False
        ) from exc

    return [EmbeddingVector(values, model, dimensions) for _, values in indexed]


async def embed_texts(
    texts: list[str],
    *,
    model: str | None = None,
    dimensions: int | None = None,
) -> list[EmbeddingVector]:
    """Embed bounded text batches, checking response shape and vector dimensions."""
    selected_model = model or settings.ai_embedding_model
    selected_dimensions = dimensions or settings.ai_embedding_dimensions
    base_url = effective_embedding_base_url()
    if not selected_model or not base_url:
        raise EmbeddingProviderError("embedding_provider_not_configured", retryable=False)

    api_key = effective_embedding_api_key()
    timeout_seconds = settings.ai_embedding_timeout_seconds
    max_attempts = settings.ai_embedding_max_attempts
    started = time.monotonic()
    last_error: EmbeddingProviderError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            vectors = await _embed_texts_once(
                texts,
                model=selected_model,
                dimensions=selected_dimensions,
                base_url=base_url,
                api_key=api_key,
                timeout_seconds=timeout_seconds,
            )
            _ = round((time.monotonic() - started) * 1000)
            return vectors
        except EmbeddingProviderError as exc:
            last_error = exc
            if not exc.retryable or attempt >= max_attempts:
                raise
            await asyncio.sleep(retry_delay_seconds(attempt, base_seconds=1, cap_seconds=30))
    if last_error is not None:
        raise last_error
    raise EmbeddingProviderError("embedding_provider_not_configured", retryable=False)
