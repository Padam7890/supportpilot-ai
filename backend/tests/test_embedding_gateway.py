from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import settings
from app.features.ai.infrastructure.embedding_gateway import (
    EmbeddingProviderError,
    embed_texts,
)


class FakeResponse:
    def __init__(self, status_code: int, body: dict[str, object]):
        self.status_code = status_code
        self._body = body

    def json(self) -> dict[str, object]:
        return self._body


class FakeClient:
    response = FakeResponse(200, {})
    request: dict[str, object] | None = None

    def __init__(self, **_kwargs: object):
        pass

    async def __aenter__(self) -> FakeClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> FakeResponse:
        FakeClient.request = {"url": url, "headers": headers, "json": json}
        return FakeClient.response


@pytest.mark.anyio
async def test_embedding_gateway_sends_server_side_config_and_validates_dimensions(monkeypatch):
    import httpx as httpx_module

    monkeypatch.setattr(settings, "ai_provider_base_url", "https://embed.example/v1")
    monkeypatch.setattr(settings, "ai_embedding_model", "embed-small")
    monkeypatch.setattr(settings, "ai_embedding_dimensions", 3)
    monkeypatch.setattr(settings, "ai_provider_api_key", SimpleNamespace(get_secret_value=lambda: "server-secret"))
    monkeypatch.setattr(httpx_module, "AsyncClient", FakeClient)
    FakeClient.response = FakeResponse(200, {"data": [
        {"index": 1, "embedding": [0.2, 0.3, 0.4]},
        {"index": 0, "embedding": [0.1, 0.2, 0.3]},
    ]})

    vectors = await embed_texts(["first", "second"])

    assert [vector.values for vector in vectors] == [[0.1, 0.2, 0.3], [0.2, 0.3, 0.4]]
    assert FakeClient.request["url"] == "https://embed.example/v1/embeddings"
    assert FakeClient.request["headers"]["authorization"] == "Bearer server-secret"


@pytest.mark.anyio
async def test_embedding_gateway_rejects_provider_errors_without_echoing_body(monkeypatch):
    import httpx as httpx_module

    monkeypatch.setattr(settings, "ai_provider_base_url", "https://embed.example/v1")
    monkeypatch.setattr(settings, "ai_embedding_model", "embed-small")
    monkeypatch.setattr(settings, "ai_embedding_dimensions", 2)
    monkeypatch.setattr(settings, "ai_provider_api_key", None)
    monkeypatch.setattr(httpx_module, "AsyncClient", FakeClient)
    FakeClient.response = FakeResponse(429, {"error": "private provider response"})

    with pytest.raises(EmbeddingProviderError) as caught:
        await embed_texts(["question"])

    assert caught.value.code == "embedding_provider_http_429"
    assert caught.value.retryable is True
    assert "private provider response" not in str(caught.value)


@pytest.mark.anyio
async def test_embedding_gateway_rejects_malformed_vector_response(monkeypatch):
    import httpx as httpx_module

    monkeypatch.setattr(settings, "ai_provider_base_url", "https://embed.example/v1")
    monkeypatch.setattr(settings, "ai_embedding_model", "embed-small")
    monkeypatch.setattr(settings, "ai_embedding_dimensions", 3)
    monkeypatch.setattr(settings, "ai_provider_api_key", None)
    monkeypatch.setattr(httpx_module, "AsyncClient", FakeClient)
    FakeClient.response = FakeResponse(200, {"data": [{"index": 0, "embedding": [1, float("nan"), 0]}]})

    with pytest.raises(EmbeddingProviderError) as caught:
        await embed_texts(["question"])

    assert caught.value.code == "embedding_provider_invalid_response"
    assert caught.value.retryable is False
