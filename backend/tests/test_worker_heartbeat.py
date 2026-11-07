import pytest

from app.workers.application.heartbeat import (
    WORKER_HEARTBEAT_KEY,
    WORKER_HEARTBEAT_TTL_SECONDS,
    WorkerHeartbeat,
    active_worker_count,
)


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.operations = []

    def zadd(self, key, members):
        self.operations.append(("zadd", key, members))
        return self

    def zremrangebyscore(self, key, minimum, maximum):
        self.operations.append(("zremrangebyscore", key, minimum, maximum))
        return self

    def expire(self, key, ttl):
        self.operations.append(("expire", key, ttl))
        return self

    async def execute(self):
        self.redis.executed = self.operations


class FakeRedis:
    def __init__(self):
        self.executed = []
        self.removed = []
        self.worker_count = 0

    def pipeline(self, *, transaction):
        assert transaction is True
        return FakePipeline(self)

    async def zrem(self, key, member):
        self.removed.append((key, member))

    async def zcount(self, key, minimum, maximum):
        assert key == WORKER_HEARTBEAT_KEY
        assert maximum == "+inf"
        self.range = (minimum, maximum)
        return self.worker_count


@pytest.mark.anyio
async def test_worker_heartbeat_publishes_expiring_private_member_and_stops_cleanly():
    redis = FakeRedis()
    heartbeat = WorkerHeartbeat(redis)

    await heartbeat.refresh(now=100)

    assert len(redis.executed) == 3
    assert redis.executed[0][0:2] == ("zadd", WORKER_HEARTBEAT_KEY)
    assert redis.executed[0][2][heartbeat._member] == 100
    assert redis.executed[1] == (
        "zremrangebyscore",
        WORKER_HEARTBEAT_KEY,
        "-inf",
        100 - WORKER_HEARTBEAT_TTL_SECONDS,
    )
    assert redis.executed[2] == ("expire", WORKER_HEARTBEAT_KEY, WORKER_HEARTBEAT_TTL_SECONDS)

    await heartbeat.stop()
    assert redis.removed == [(WORKER_HEARTBEAT_KEY, heartbeat._member)]


@pytest.mark.anyio
async def test_worker_health_counts_only_recent_heartbeats():
    redis = FakeRedis()
    redis.worker_count = 3

    assert await active_worker_count(redis, now=200) == 3
    assert redis.range == (200 - WORKER_HEARTBEAT_TTL_SECONDS, "+inf")
