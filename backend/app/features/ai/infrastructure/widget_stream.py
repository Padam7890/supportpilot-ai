"""Short-lived, attempt-scoped reply deltas shared across worker and API processes."""

import time
from contextlib import asynccontextmanager
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

STREAM_TTL_SECONDS = 120
STREAM_MAX_ENTRIES = 512


def reply_stream_key(org: UUID, conversation: UUID, execution: UUID, attempt: int) -> str:
    return f"widget:reply-stream:{org}:{conversation}:{execution}:{attempt}"


@asynccontextmanager
async def publish_widget_deltas(
    org: UUID, conversation: UUID, execution: UUID, attempt: int, documents: list[str]
):
    key = reply_stream_key(org, conversation, execution, attempt)
    buffered = ""
    last_write = 0.0
    available = True
    async with Redis.from_url(settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5) as redis:
        async def flush() -> None:
            nonlocal available, buffered, last_write
            if not available or not buffered:
                return
            try:
                async with redis.pipeline(transaction=True) as pipe:
                    pipe.xadd(key, {"text": buffered, "documents": ",".join(documents)}, maxlen=STREAM_MAX_ENTRIES, approximate=False)
                    pipe.expire(key, STREAM_TTL_SECONDS)
                    await pipe.execute()
                last_write = time.monotonic()
            except RedisError:
                available = False  # Final reply still uses PostgreSQL.
            buffered = ""

        async def publish(delta: str) -> None:
            nonlocal buffered
            if available:
                buffered += delta
                if len(buffered) >= 512 or time.monotonic() - last_write >= 0.12:
                    await flush()

        yield publish
        await flush()
