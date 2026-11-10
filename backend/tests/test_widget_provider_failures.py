import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from app.core.config import settings
from app.features.ai.application.widget_stream_context import STREAM_SOURCE_IDS_KEY
from app.features.ai.domain.failure_codes import is_retryable_ai_failure
from app.features.ai.infrastructure.llm_gateway import (
    AIProviderError,
    generate_completion,
    is_provider_configured,
    provider_configuration_error,
    provider_http_error,
    stream_completion,
)
from app.services import ai_worker as worker
from app.services.widget_ai import AI_TEMPORARY_FAILURE_REPLY, WIDGET_PROVIDER_UNAVAILABLE_REPLY


@pytest.mark.parametrize(
    ("url", "model", "code"),
    [
        (None, "test-model", "provider_not_configured"),
        ("https://gateway.example/v1", "  ", "provider_not_configured"),
        ("https://api.openai.com/v1", "test-model", "provider_key_missing"),
        ("https://gateway.example/v1/chat/completions", "test-model", "provider_url_invalid"),
    ],
)
def test_local_provider_configuration(monkeypatch, url, model, code):
    monkeypatch.setattr(settings, "ai_provider_base_url", url)
    monkeypatch.setattr(settings, "ai_model", model)
    monkeypatch.setattr(settings, "ai_provider_api_key", None)
    assert not is_provider_configured()
    assert provider_configuration_error().code == code


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["authentication", "timeout", "quota", "rate_limit"])
@pytest.mark.parametrize("streaming", [False, True])
async def test_gateway_preserves_safe_failure_reason(monkeypatch, failure, streaming):
    monkeypatch.setattr(settings, "ai_provider_base_url", "https://gateway.example/v1")
    monkeypatch.setattr(settings, "ai_model", "test-model")
    original_client = httpx.AsyncClient
    expected = {
        "authentication": ("provider_http_401", 401, "expired_secret_key", False),
        "timeout": ("provider_timeout", None, None, True),
        "quota": ("provider_http_429", 429, "insufficient_quota", False),
        "rate_limit": ("provider_http_429", 429, "rate_limit_exceeded", True),
    }[failure]
    code, status, reason, retryable = expected

    def handler(request):
        if status is None:
            raise httpx.ReadTimeout("private transport detail", request=request)
        return httpx.Response(status, json={"error": {"code": reason, "message": "secret key value"}})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(handler), **kwargs
    ))
    with pytest.raises(AIProviderError) as caught:
        messages = [{"role": "user", "content": "Can I return an item?"}]
        if streaming:
            async for _ in stream_completion(messages):
                pytest.fail("a failed stream must not emit a delta")
        else:
            await generate_completion(messages)
    error = caught.value
    assert (error.code, error.http_status, error.provider_reason) == (code, status, reason)
    assert is_retryable_ai_failure(error) is retryable
    assert "secret key value" not in str(error)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("scenario", "attempt", "decision"),
    [
        ("missing", 1, "not_retryable"),
        ("auth", 1, "not_retryable"),
        ("timeout", 1, "retry_scheduled"),
        ("timeout", 2, "retry_exhausted"),
        ("retrieval", 1, "not_retryable"),
        ("success", 1, None),
        ("stream_existing_chat", 1, None),
        ("stream_grounded_follow_up", 1, None),
        ("revoked_follow_up_source", 1, None),
        ("private_follow_up", 1, None),
    ],
)
async def test_widget_worker_keeps_retrieval_and_provider_outcomes_separate(
    monkeypatch, caplog, scenario, attempt, decision
):
    from logging import INFO

    caplog.set_level(INFO, logger=worker.__name__)
    org, execution_id = uuid4(), uuid4()
    row = SimpleNamespace(
        kind="widget_reply", question="What is your return policy?", ai_agent_id=uuid4(),
        attempt_count=attempt, max_attempts=2, correlation_id=None, status="running",
        instructions=None, delivery_mode="auto_reply", conversation_id=uuid4(),
    )
    citations = [{"document_id": str(uuid4())}]
    previous_document_id = str(uuid4())
    follow_up_scenarios = {"stream_grounded_follow_up", "revoked_follow_up_source", "private_follow_up"}
    history = [{"sender": "assistant", "content": "Previous private order details."}]
    if scenario in follow_up_scenarios:
        row.question = "What about damaged items?"
        history = [
            {"sender": "customer", "content": "What is your return policy?"},
            {"sender": "assistant", "content": "Returns within 30 days."},
            {"sender": "customer", "content": row.question},
        ]
        if scenario == "private_follow_up":
            history[1]["content"] = "Previous private order details."
        else:
            history[1][STREAM_SOURCE_IDS_KEY] = json.dumps([previous_document_id])
    empty = (row, row.question, [], [], [], [], {})
    grounded = (row, row.question, history, [{"excerpt": "Returns within 30 days."}], citations, [], {})
    loading = AsyncMock(side_effect=[empty, RuntimeError("secret DB error") if scenario == "retrieval" else grounded])
    monkeypatch.setattr(worker, "load_execution_context", loading)
    monkeypatch.setattr(worker, "widget_reply_is_stale", AsyncMock(return_value=False))
    monkeypatch.setattr(worker, "process_widget_shopping_execution", AsyncMock(return_value=False))
    monkeypatch.setattr(worker, "resolve_customer_routing", AsyncMock(
        return_value=SimpleNamespace(tool_outcome=lambda: {"primary_intent": "policy"})
    ))
    monkeypatch.setattr(worker, "apply_routing_to_widget_plan", lambda *_args: SimpleNamespace(route="knowledge"))
    monkeypatch.setattr(settings, "widget_ai_streaming_enabled", scenario in follow_up_scenarios | {"stream_existing_chat"})
    check_citations = AsyncMock(return_value=scenario != "revoked_follow_up_source")
    monkeypatch.setattr(worker, "citations_remain_authorized", check_citations)
    publish = AsyncMock()

    published_sources = []

    @asynccontextmanager
    async def fake_publisher(*args):
        published_sources.extend(args[-1])
        yield publish

    monkeypatch.setattr(worker, "publish_widget_deltas", fake_publisher)
    monkeypatch.setattr(worker, "provider_configuration_error", lambda: (
        AIProviderError("provider_not_configured", "missing settings") if scenario == "missing" else None
    ))
    failures = {
        "auth": provider_http_error(401, b'{"error":{"code":"invalid_api_key","message":"secret key value"}}'),
        "timeout": AIProviderError("provider_timeout", "secret transport detail"),
    }
    generate = AsyncMock(
        side_effect=failures.get(scenario),
        return_value={"draft": "Returns are accepted within 30 days.", "usage": {}, "model_name": "test-model"},
    )
    monkeypatch.setattr(worker, "create_grounded_draft", generate)
    finish = AsyncMock()
    monkeypatch.setattr(worker, "finish_widget_reply", finish)
    db = AsyncMock()
    db.scalar.return_value = row
    monkeypatch.setattr(worker, "SessionLocal", lambda: db)
    db.__aenter__.return_value = db
    monkeypatch.setattr(worker, "set_tenant_context", AsyncMock())

    await worker.process_ai_execution(org, execution_id)

    if decision:
        entries = [
            json.loads(record.message.removeprefix("ai_execution_event "))
            for record in caplog.records if "ai_execution_retry_decision" in record.message
        ]
        assert entries[0]["decision"] == decision
        assert entries[0]["retry_count"] == attempt - 1
        assert "secret" not in caplog.text
    if scenario in {"missing", "retrieval"}:
        generate.assert_not_awaited()
    if decision == "retry_scheduled":
        assert row.status == "queued"
        assert row.error_code == "provider_timeout"
        finish.assert_not_awaited()
    elif scenario in follow_up_scenarios:
        arguments = generate.await_args.kwargs
        if scenario == "stream_grounded_follow_up":
            assert arguments["on_delta"] is publish
            assert arguments["conversation_context"][1]["content"] == "Returns within 30 days."
            assert set(published_sources) == {citations[0]["document_id"], previous_document_id}
            assert finish.await_args.kwargs["stream_source_ids"] == published_sources
        else:
            assert "on_delta" not in arguments
            assert not published_sources
            if scenario == "revoked_follow_up_source":
                assert arguments["conversation_context"] == []
        if scenario == "private_follow_up":
            check_citations.assert_not_awaited()
        else:
            assert check_citations.await_args.kwargs["citations"] == [{"document_id": previous_document_id}]
    elif scenario in {"success", "stream_existing_chat"}:
        if scenario == "stream_existing_chat":
            assert generate.await_args.kwargs["on_delta"] is publish
            assert generate.await_args.kwargs["conversation_context"] == []
        else:
            assert generate.await_args.kwargs["conversation_context"] == history
        assert finish.await_args.kwargs["citations"] == citations
        assert finish.await_args.kwargs["reply_status"] == "sent"
    elif scenario == "retrieval":
        assert finish.await_args.kwargs["draft"] == AI_TEMPORARY_FAILURE_REPLY
        assert finish.await_args.kwargs["failure_code"] == "knowledge_retrieval_failed"
    else:
        assert finish.await_args.kwargs["draft"] == WIDGET_PROVIDER_UNAVAILABLE_REPLY
        if scenario == "auth":
            assert entries[0]["provider_http_status"] == 401
