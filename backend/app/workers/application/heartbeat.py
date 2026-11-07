"""Shared Redis heartbeat for the durable worker process."""

from __future__ import annotations

import time
from uuid import uuid4

from redis.asyncio import Redis

WORKER_HEARTBEAT_KEY = "supportpilot:workers:heartbeats"
WORKER_HEARTBEAT_TTL_SECONDS = 30


class WorkerHeartbeat:
    """Publish process liveness without exposing host or process identifiers."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis
        self._member = str(uuid4())

    async def refresh(self, *, now: float | None = None) -> None:
        timestamp = time.time() if now is None else now
        cutoff = timestamp - WORKER_HEARTBEAT_TTL_SECONDS
        pipeline = self._redis.pipeline(transaction=True)
        pipeline.zadd(WORKER_HEARTBEAT_KEY, {self._member: timestamp})
        pipeline.zremrangebyscore(WORKER_HEARTBEAT_KEY, "-inf", cutoff)
        pipeline.expire(WORKER_HEARTBEAT_KEY, WORKER_HEARTBEAT_TTL_SECONDS)
        await pipeline.execute()

    async def stop(self) -> None:
        await self._redis.zrem(WORKER_HEARTBEAT_KEY, self._member)


async def active_worker_count(redis: Redis, *, now: float | None = None) -> int:
    timestamp = time.time() if now is None else now
    cutoff = timestamp - WORKER_HEARTBEAT_TTL_SECONDS
    return int(await redis.zcount(WORKER_HEARTBEAT_KEY, cutoff, "+inf"))
