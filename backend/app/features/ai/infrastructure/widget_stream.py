"""Short-lived, attempt-scoped reply deltas shared across worker and API processes."""

import logging
import time
from contextlib import asynccontextmanager
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

STREAM_TTL_SECONDS = 120
STREAM_MAX_ENTRIES = 12_000  # One entry per character at the provider output limit.
logger = logging.getLogger(__name__)


def reply_stream_key(org: UUID, conversation: UUID, execution: UUID, attempt: int) -> str:
    return f"widget:reply-stream:{org}:{conversation}:{execution}:{attempt}"


@asynccontextmanager
async def publish_widget_deltas(
    org: UUID, conversation: UUID, execution: UUID, attempt: int, documents: list[str]
):
    key = reply_stream_key(org, conversation, execution, attempt)
    available = True
    first_published = False
    document_ids = ",".join(documents)
    async with Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5) as redis:
        async def publish(delta: str) -> None:
            nonlocal available, first_published
            if not available or not delta:
                return
            try:
                async with redis.pipeline(transaction=True) as pipe:
                    pipe.xadd(
                        key, {"text": delta, "documents": document_ids},
                        maxlen=STREAM_MAX_ENTRIES, approximate=False,
                    )
                    pipe.expire(key, STREAM_TTL_SECONDS)
                    offset, _ = await pipe.execute()
                if not first_published:
                    first_published = True
                    logger.info(
                        "widget_stream_first_publish execution_id=%s attempt=%d at_ms=%d redis_id=%s",
                        execution, attempt, time.time_ns() // 1_000_000, offset.decode(),
                    )
            except RedisError:
                available = False  # Final reply still uses PostgreSQL.

        yield publish
