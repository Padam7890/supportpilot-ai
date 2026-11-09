"""Validated, server-side OpenAI-compatible embedding gateway."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import settings


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


def is_embedding_provider_configured() -> bool:
    return bool(settings.ai_provider_base_url and settings.ai_embedding_model)


def _validate_provider_url(base_url: str) -> None:
    parsed = urlsplit(base_url)
    local_http_host = parsed.scheme == "http" and parsed.hostname in {
        "localhost", "127.0.0.1", "::1"
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


async def embed_texts(
    texts: list[str],
    *,
    model: str | None = None,
    dimensions: int | None = None,
) -> list[EmbeddingVector]:
    """Embed bounded text batches, checking response shape and vector dimensions."""
    import httpx

    selected_model = model or settings.ai_embedding_model
    selected_dimensions = dimensions or settings.ai_embedding_dimensions
    base_url = (settings.ai_provider_base_url or "").rstrip("/")
    if not selected_model or not base_url:
        raise EmbeddingProviderError("embedding_provider_not_configured", retryable=False)
    if not texts or len(texts) > settings.ai_embedding_batch_size:
        raise ValueError("embedding batch size is outside configured bounds")
    if any(not isinstance(text, str) or not text.strip() or len(text) > 20_000 for text in texts):
        raise ValueError("embedding input is invalid")
    _validate_provider_url(base_url)

    headers = {"content-type": "application/json"}
    if settings.ai_provider_api_key:
        headers["authorization"] = f"Bearer {settings.ai_provider_api_key.get_secret_value()}"
    payload: dict[str, object] = {"model": selected_model, "input": texts}
    payload["dimensions"] = selected_dimensions
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.ai_provider_timeout_seconds) as client:
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
                raise ValueError("unexpected embedding item")
            index = item.get("index", fallback_index)
            raw_values = item.get("embedding")
            if isinstance(index, bool) or not isinstance(index, int) or not isinstance(raw_values, list):
                raise ValueError("unexpected embedding shape")
            if len(raw_values) != selected_dimensions:
                raise ValueError("embedding dimension mismatch")
            values = [float(value) for value in raw_values]
            if any(not math.isfinite(value) for value in values):
                raise ValueError("non-finite embedding value")
            indexed.append((index, values))
        indexed.sort(key=lambda row: row[0])
        if [index for index, _ in indexed] != list(range(len(texts))):
            raise ValueError("embedding indices are incomplete")
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise EmbeddingProviderError("embedding_provider_invalid_response", retryable=False) from exc

    # Keep telemetry safe: only model, vector count, and elapsed time are exposed.
    _ = round((time.monotonic() - started) * 1000)
    return [EmbeddingVector(values, selected_model, selected_dimensions) for _, values in indexed]
