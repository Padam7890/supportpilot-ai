import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.workers.application.contracts import ClaimedJob
from app.workers.application.dispatcher import WorkerDispatcher
from app.workers.domain.retry_policy import retry_delay_seconds


class FakeRepository:
    def __init__(self, organizations):
        self.organizations = organizations

    async def approved_organizations(self, after=None):
        return [org for org in self.organizations if after is None or org > after]

    async def failed_job_counts(self, organization_id):
        return {}


class FakeHandler:
    def __init__(self, kind, claimed_orgs, processed):
        self.kind = kind
        self.claimed_orgs = claimed_orgs
        self.processed = processed

    async def claim(self, organization_id):
        if organization_id not in self.claimed_orgs:
            return None
        return ClaimedJob(self.kind, organization_id, uuid4())

    async def process(self, job):
        self.processed.append((self.kind, job.organization_id))


@pytest.mark.anyio
async def test_dispatcher_fairly_rotates_tenants_and_job_families(monkeypatch):
    import app.workers.application.dispatcher as dispatcher_module

    async def no_reconcile(_organizations):
        return None

    monkeypatch.setattr(dispatcher_module, "enqueue_reconciliation", no_reconcile)
    organization_a, organization_b = sorted((uuid4(), uuid4()))
    processed = []
    handlers = [
        FakeHandler("ai", {organization_a, organization_b}, processed),
        FakeHandler("catalog", {organization_a, organization_b}, processed),
    ]
    dispatcher = WorkerDispatcher(
        handlers=handlers,
        repository=FakeRepository([organization_a, organization_b]),
        job_timeout_seconds=1,
    )
    dispatcher._last_reconciliation = datetime.now(UTC)

    assert await dispatcher.dispatch_one()
    assert await dispatcher.dispatch_one()
    assert processed == [("ai", organization_a), ("catalog", organization_b)]


@pytest.mark.anyio
async def test_dispatcher_bounds_handler_time_and_keeps_runtime_alive(monkeypatch):
    import app.workers.application.dispatcher as dispatcher_module

    async def no_reconcile(_organizations):
        return None

    monkeypatch.setattr(dispatcher_module, "enqueue_reconciliation", no_reconcile)
    organization_id = uuid4()

    class SlowHandler(FakeHandler):
        async def process(self, job):
            await asyncio.sleep(0.1)

    dispatcher = WorkerDispatcher(
        handlers=[SlowHandler("slow", {organization_id}, [])],
        repository=FakeRepository([organization_id]),
        job_timeout_seconds=0.001,
    )
    dispatcher._last_reconciliation = datetime.now(UTC)
    assert await dispatcher.dispatch_one()


@pytest.mark.parametrize(
    ("attempt", "random_value", "expected"),
    [(1, 0.5, 5), (2, 0.5, 10), (8, 1.0, 60)],
)
def test_retry_policy_uses_bounded_exponential_full_jitter(attempt, random_value, expected):
    assert (
        retry_delay_seconds(
            attempt,
            base_seconds=10,
            cap_seconds=60,
            random_value=random_value,
        )
        == expected
    )


def test_retry_policy_honors_provider_retry_after_with_cap():
    assert (
        retry_delay_seconds(
            2,
            retry_after_seconds=1200,
            cap_seconds=900,
        )
        == 900
    )


def test_retry_policy_rejects_invalid_attempt_and_jitter():
    with pytest.raises(ValueError):
        retry_delay_seconds(0)
    with pytest.raises(ValueError):
        retry_delay_seconds(1, random_value=1.5)


@pytest.mark.anyio
async def test_worker_runtime_never_exceeds_configured_concurrency(monkeypatch):
    import app.workers.runtime as runtime_module

    stop = asyncio.Event()

    class ConcurrentDispatcher:
        def __init__(self, *, job_timeout_seconds):
            assert job_timeout_seconds > 0
            self.active = 0
            self.max_active = 0
            self.completed = 0

        async def dispatch_one(self):
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            await asyncio.sleep(0.005)
            self.active -= 1
            self.completed += 1
            if self.completed >= 9:
                stop.set()
            return True

    dispatcher = ConcurrentDispatcher(job_timeout_seconds=30)
    monkeypatch.setattr(runtime_module, "WorkerDispatcher", lambda **_kwargs: dispatcher)
    await runtime_module.run_worker(concurrency=3, stop_event=stop)
    assert dispatcher.completed >= 9
    assert dispatcher.max_active == 3


@pytest.mark.anyio
async def test_worker_runtime_recovers_from_dispatch_iteration_failure(monkeypatch):
    import app.workers.runtime as runtime_module

    stop = asyncio.Event()

    class RecoveringDispatcher:
        def __init__(self, *, job_timeout_seconds):
            assert job_timeout_seconds > 0
            self.attempts = 0

        async def dispatch_one(self):
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("database temporarily unavailable")
            stop.set()
            return False

    dispatcher = RecoveringDispatcher(job_timeout_seconds=30)
    monkeypatch.setattr(runtime_module, "WorkerDispatcher", lambda **_kwargs: dispatcher)
    await runtime_module.run_worker(poll_seconds=0.001, concurrency=1, stop_event=stop)
    assert dispatcher.attempts == 2
