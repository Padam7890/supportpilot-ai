import asyncio
import json
import os
from contextlib import aclosing
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from redis.asyncio import Redis

from app.core.config import settings
from app.features.ai.infrastructure.llm_gateway import (
    AIProviderError,
    CompletionDelta,
    CompletionEnd,
    stream_completion,
)
from app.features.ai.infrastructure.widget_stream import publish_widget_deltas, reply_stream_key
from app.features.widgets.reply_stream import ReplyEvent, StreamPayload, encode_event
from app.services.ai_worker import _can_stream_transcript, _stream_conversation_context

MESSAGES = [{"role": "user", "content": "How long does shipping take?"}]


@pytest.fixture
def provider(monkeypatch):
    original_client = httpx.AsyncClient
    monkeypatch.setattr(settings, "ai_provider_base_url", "https://example.com/v1")
    monkeypatch.setattr(settings, "ai_model", "test-model")

    def install(body):
        async def handle(request):
            assert request.url.path == "/v1/chat/completions"
            payload = json.loads(request.content)
            assert payload["stream"] and payload["stream_options"]["include_usage"]
            return httpx.Response(200, stream=body)

        monkeypatch.setattr(
            httpx, "AsyncClient",
            lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs),
        )
    return install


@pytest.mark.anyio
async def test_first_provider_delta_arrives_before_completion(provider):
    finish = asyncio.Event()

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"Shipping "}}]}\n\n'
            await finish.wait()
            yield b'data: {"choices":[{"delta":{"content":"takes 2 days."},"finish_reason":"stop"}]}\n\n'
            yield b'data: {"choices":[],"usage":{"total_tokens":21}}\n\ndata: [DONE]\n\n'

    provider(Body())
    async with aclosing(stream_completion(MESSAGES)) as stream:
        assert await anext(stream) == CompletionDelta("Shipping ")
        assert not finish.is_set()
        finish.set()
        assert await anext(stream) == CompletionDelta("takes 2 days.")
        assert await anext(stream) == CompletionEnd(
            {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 21}, "test-model"
        )


@pytest.mark.anyio
async def test_interrupted_provider_stream_does_not_report_completion(provider):
    class Body(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'

    provider(Body())
    async with aclosing(stream_completion(MESSAGES)) as stream:
        assert await anext(stream) == CompletionDelta("partial")
        with pytest.raises(AIProviderError, match="ended before completion"):
            await anext(stream)


def test_event_has_scoped_sequence_and_validated_payload():
    row = SimpleNamespace(id=uuid4(), attempt_count=2)
    conversation = uuid4()
    frame = encode_event(row, conversation, "message.delta", "123-0", text="Shipping")
    event = ReplyEvent.model_validate_json(frame.split("data: ", 1)[1])
    assert event.sequence == f"{row.id}:2:123-0"
    assert event.conversation_id == conversation
    with pytest.raises(ValidationError):
        ReplyEvent(
            execution_id=row.id, conversation_id=conversation, sequence=event.sequence,
            event_type="message.completed", timestamp=datetime.now(UTC),
            payload=StreamPayload(text="uncommitted content"),
        )


def test_transcript_allows_social_turns_but_excludes_historical_order_replies():
    from app.features.ai.application.conversational_intents import widget_conversational_reply

    greeting = widget_conversational_reply("hello")
    assert greeting is not None
    transcript = [
        {"sender": "customer", "content": "hello"},
        {"sender": "assistant", "content": greeting[0]},
        {"sender": "customer", "content": "What is the return policy?"},
    ]
    assert _can_stream_transcript(transcript)
    transcript[1]["content"] = "Your verified order #123 is on the way."
    assert not _can_stream_transcript(transcript)
    assert _stream_conversation_context("What is the return policy?", transcript) == []
    assert _stream_conversation_context("What about that one?", transcript) is None


@pytest.mark.anyio
async def test_redis_replay_uses_exclusive_cursor_and_attempt_scope(monkeypatch):
    redis_url = os.environ.get("TEST_WIDGET_STREAM_REDIS_URL")
    if not redis_url:
        pytest.skip("requires an isolated Redis server")
    monkeypatch.setattr(settings, "redis_url", redis_url)
    org, conversation, execution, doc = (uuid4() for _ in range(4))
    key = reply_stream_key(org, conversation, execution, 1)
    async with Redis.from_url(redis_url, decode_responses=True) as reader:
        async with publish_widget_deltas(org, conversation, execution, 1, [str(doc)]) as publish:
            await publish("First ")
            entries = (await reader.xread({key: "0-0"}, count=4, block=250))[0][1]
            assert entries[0][1]["text"] == "First "
            waiting = asyncio.create_task(reader.xread({key: entries[0][0]}, count=4, block=1000))
            await asyncio.sleep(0)
            assert not waiting.done()
            await publish("second")
            resumed = await asyncio.wait_for(waiting, timeout=0.75)
            assert [item["text"] for _, item in resumed[0][1]] == ["second"]
        assert await reader.xrange(reply_stream_key(org, conversation, execution, 2)) == []
        assert 0 < await reader.ttl(key) <= 120
        await reader.delete(key)


@pytest.mark.anyio
async def test_stream_endpoint_requires_conversation_scoped_visitor_token(client, monkeypatch):
    from datetime import timedelta

    from app.core.security import create_widget_visitor_token

    monkeypatch.setattr(settings, "widget_ai_streaming_enabled", True)
    conversation, other_conversation, organization = (uuid4() for _ in range(3))
    path = f"/api/v1/widget/conversations/{conversation}/reply-stream"
    assert (await client.get(path)).status_code == 401
    token = create_widget_visitor_token(
        organization_id=str(organization),
        conversation_id=str(other_conversation),
        widget_public_id="widget-public-id-example",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    denied = await client.get(path, headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403
    assert "text/event-stream" not in denied.headers["content-type"]


def test_terminal_event_rejects_uncommitted_text():
    row = SimpleNamespace(id=uuid4(), attempt_count=1)
    conversation = uuid4()
    with pytest.raises(ValidationError):
        ReplyEvent(
            execution_id=row.id,
            conversation_id=conversation,
            sequence=f"{row.id}:1:0-0",
            event_type="execution.cancelled",
            timestamp=datetime.now(UTC),
            payload=StreamPayload(text="Unsafe provisional content"),
        )


def test_completed_event_requires_persisted_message_id():
    row = SimpleNamespace(id=uuid4(), attempt_count=1)
    conversation = uuid4()
    with pytest.raises(ValidationError):
        ReplyEvent(
            execution_id=row.id,
            conversation_id=conversation,
            sequence=f"{row.id}:1:0-0",
            event_type="message.completed",
            timestamp=datetime.now(UTC),
            payload=StreamPayload(),
        )


def test_delta_event_cannot_contain_terminal_message_id():
    row = SimpleNamespace(id=uuid4(), attempt_count=1)
    conversation = uuid4()
    with pytest.raises(ValidationError):
        ReplyEvent(
            execution_id=row.id,
            conversation_id=conversation,
            sequence=f"{row.id}:1:1-0",
            event_type="message.delta",
            timestamp=datetime.now(UTC),
            payload=StreamPayload(text="partial", message_id=uuid4()),
        )
