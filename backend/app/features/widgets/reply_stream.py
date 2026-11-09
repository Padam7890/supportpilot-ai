"""Visitor-authorized SSE for provisional storefront AI replies."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from redis.exceptions import RedisError
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.features.ai.application.retrieval_search import citations_remain_authorized
from app.features.ai.infrastructure.widget_stream import reply_stream_key
from app.features.widgets.shared import require_visitor_conversation
from app.models import AIExecution, Message

router = APIRouter(prefix="/widget", tags=["Public storefront chat"])
logger = logging.getLogger(__name__)
STREAM_WINDOW_SECONDS = 40
REDIS_BLOCK_MS = 250
QUEUED_POLL_SECONDS = 0.1
KEEPALIVE_SECONDS = 10
READ_COUNT = 16
REDIS_START = "0-0"
STATUS_OFFSET = "0-1"
TERMINAL_OFFSET = "18446744073709551615-18446744073709551615"


class StreamPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str | None = Field(default=None, max_length=16_000)
    message_id: UUID | None = None
    status: Literal["queued", "running", "retrying"] | None = None


class ReplyEvent(BaseModel):
    execution_id: UUID
    conversation_id: UUID
    sequence: str
    event_type: Literal[
        "execution.queued", "execution.started", "execution.status", "message.delta",
        "message.completed", "execution.failed", "execution.cancelled", "conversation.handoff",
    ]
    timestamp: datetime
    payload: StreamPayload

    @model_validator(mode="after")
    def validate_payload(self):
        fields = self.payload.model_dump(exclude_none=True).keys()
        required = {
            "message.delta": {"text"},
            "message.completed": {"message_id"},
            "execution.queued": {"status"},
            "execution.started": {"status"},
            "execution.status": {"status"},
        }.get(self.event_type, set())
        if self.event_type == "execution.failed" and fields == {"message_id"}:
            return self
        if fields != required:
            raise ValueError("Invalid reply stream payload")
        return self


def encode_event(row: AIExecution, conversation_id: UUID, event_type, offset=None, **payload) -> str:
    if offset is None:
        if event_type == "execution.started":
            offset = REDIS_START
        elif event_type in {"execution.queued", "execution.status"}:
            offset = STATUS_OFFSET
        else:
            offset = TERMINAL_OFFSET
    event = ReplyEvent(
        execution_id=row.id, conversation_id=conversation_id,
        sequence=f"{row.id}:{row.attempt_count}:{offset}",
        event_type=event_type, timestamp=datetime.now(UTC), payload=StreamPayload(**payload),
    )
    return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {event.model_dump_json(exclude_none=True)}\n\n"


async def latest_execution(db, org: UUID, conversation_id: UUID) -> AIExecution | None:
    return await db.scalar(
        select(AIExecution).where(
            AIExecution.organization_id == org, AIExecution.conversation_id == conversation_id,
            AIExecution.kind == "widget_reply",
        ).order_by(AIExecution.created_at.desc(), AIExecution.id.desc()).limit(1)
    )


async def can_release_deltas(db, row: AIExecution, conversation_id: UUID) -> bool:
    # Any later message, including a teammate note, supersedes a provisional reply.
    latest = await db.scalar(
        select(Message.id).where(
            Message.organization_id == row.organization_id, Message.conversation_id == conversation_id,
        ).order_by(Message.created_at.desc(), Message.id.desc()).limit(1)
    )
    return row.source_message_id is not None and latest == row.source_message_id


async def reply_events(
    request: Request, conversation_id: UUID, authorization: str | None,
    execution_id: UUID, after: str,
) -> AsyncIterator[str]:
    started_at = time.monotonic()
    deadline = started_at + STREAM_WINDOW_SECONDS
    redis = getattr(request.app.state, "redis", None)
    cursor = REDIS_START
    previous_state = None
    delivered_deltas = 0
    entries = []
    next_keepalive = started_at + KEEPALIVE_SECONDS
    while time.monotonic() < deadline and not await request.is_disconnected():
        frames = []
        terminal = False
        stream_key = None
        async with SessionLocal() as db:
            try:
                widget, conversation, _ = await require_visitor_conversation(
                    request, conversation_id, authorization, db, rate_limit=False
                )
            except HTTPException:
                return
            row = await latest_execution(db, widget.organization_id, conversation_id)
            if row is None or row.id != execution_id:
                return
            state = (row.status, row.attempt_count)
            if conversation.ai_mode != "ai":
                frames.append(encode_event(row, conversation_id, "conversation.handoff"))
                terminal = True
            elif not widget.ai_enabled or widget.ai_reply_mode != "auto_reply" or row.ai_agent_id != conversation.ai_agent_id:
                frames.append(encode_event(row, conversation_id, "execution.cancelled"))
                terminal = True
            elif row.status in {"succeeded", "failed"}:
                message_id = await db.scalar(select(Message.id).where(
                    Message.organization_id == widget.organization_id,
                    Message.conversation_id == conversation_id,
                    Message.source_ai_execution_id == row.id,
                    Message.sender_type == "assistant",
                ))
                event_type = (
                    "execution.failed" if row.status == "failed" or row.error_code
                    else "message.completed" if message_id is not None
                    else "execution.cancelled"
                )
                frames.append(encode_event(row, conversation_id, event_type, message_id=message_id if event_type != "execution.cancelled" else None))
                terminal = True
            elif not await can_release_deltas(db, row, conversation_id):
                frames.append(encode_event(row, conversation_id, "execution.cancelled"))
                terminal = True
            elif row.status == "queued" and state != previous_state:
                frames.append(encode_event(
                    row, conversation_id, "execution.status" if row.attempt_count else "execution.queued",
                    status="retrying" if row.attempt_count else "queued",
                ))
            elif row.status == "running":
                if state != previous_state:
                    prefix = f"{row.id}:{row.attempt_count}:"
                    cursor = after.removeprefix(prefix) if after.startswith(prefix) else REDIS_START
                    if cursor in {REDIS_START, STATUS_OFFSET}:
                        frames.append(encode_event(row, conversation_id, "execution.started", status="running"))
                stream_key = reply_stream_key(
                    widget.organization_id, conversation_id, row.id, row.attempt_count
                )
                if entries and entries[0][0] == stream_key:
                    batch = entries[0][1]
                    documents = {
                        item for _, entry in batch for item in entry["documents"].split(",") if item
                    }
                    citations = [{"document_id": item} for item in sorted(documents)]
                    if not citations or not await citations_remain_authorized(
                        db, organization_id=widget.organization_id, ai_agent_id=row.ai_agent_id,
                        citations=citations,
                    ):
                        frames = [encode_event(row, conversation_id, "execution.cancelled")]
                        terminal = True
                    else:
                        for cursor, entry in batch:
                            delivered_deltas += 1
                            if delivered_deltas == 1:
                                logger.info(
                                    "widget_stream_first_delta execution_id=%s attempt=%d elapsed_ms=%d "
                                    "at_ms=%d redis_id=%s",
                                    execution_id, row.attempt_count,
                                    round((time.monotonic() - started_at) * 1000),
                                    time.time_ns() // 1_000_000, cursor,
                                )
                            frames.append(encode_event(
                                row, conversation_id, "message.delta", cursor, text=entry["text"],
                            ))
            previous_state = state
        for frame in frames:
            yield frame
        if terminal:
            logger.info(
                "widget_stream_closed execution_id=%s deltas=%d",
                execution_id, delivered_deltas,
            )
            return
        if time.monotonic() >= next_keepalive:
            yield ": keepalive\n\n"
            next_keepalive = time.monotonic() + KEEPALIVE_SECONDS
        # Wait outside the transaction, then recheck authorization before yielding
        # any text, including entries replayed after a reconnect.
        entries = []
        if stream_key is not None and redis is not None:
            try:
                async with asyncio.timeout(0.75):
                    entries = await redis.xread(
                        {stream_key: cursor}, count=READ_COUNT, block=REDIS_BLOCK_MS,
                    )
            except (RedisError, TimeoutError):
                return
        else:
            await asyncio.sleep(QUEUED_POLL_SECONDS)



@router.get(
    "/conversations/{conversation_id}/reply-stream",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def stream_widget_reply(
    request: Request, conversation_id: UUID,
    authorization: Annotated[str | None, Header()] = None,
    after: Annotated[str, Query(max_length=100, pattern=r"^(?:[0-9a-f-]{36}:\d{1,5}:\d{1,20}-\d{1,20})?$")] = "",
):
    if not settings.widget_ai_streaming_enabled:
        raise HTTPException(status_code=404, detail="Reply streaming is unavailable")
    async with SessionLocal() as db:
        widget, conversation, _ = await require_visitor_conversation(
            request, conversation_id, authorization, db
        )
        if not widget.ai_enabled or widget.ai_reply_mode != "auto_reply" or conversation.ai_mode != "ai":
            return StreamingResponse(iter(()), media_type="text/event-stream")
        row = await latest_execution(db, widget.organization_id, conversation_id)
    if row is None or row.delivery_mode != "auto_reply":
        return StreamingResponse(iter(()), media_type="text/event-stream")
    return StreamingResponse(
        reply_events(request, conversation_id, authorization, row.id, after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store, no-transform", "X-Accel-Buffering": "no"},
    )
