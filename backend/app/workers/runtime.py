"""Bounded-concurrency worker runtime with graceful signal shutdown."""

import asyncio
import logging
import signal

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings
from app.features.ai.infrastructure.llm_gateway import provider_configuration_error
from app.workers.application.dispatcher import WorkerDispatcher
from app.workers.application.heartbeat import WorkerHeartbeat

logger = logging.getLogger(__name__)
WORKER_HEARTBEAT_INTERVAL_SECONDS = 5


async def _worker_loop(
    worker_number: int,
    dispatcher: WorkerDispatcher,
    stop_event: asyncio.Event,
    poll_seconds: float,
) -> None:
    while not stop_event.is_set():
        try:
            did_work = await dispatcher.dispatch_one()
        except (
            Exception
        ) as exc:  # keep the worker available through transient database/runtime failures
            logger.exception(
                "worker_dispatch_iteration_failed",
                extra={"worker_number": worker_number, "error_type": type(exc).__name__},
            )
            did_work = False
        if not did_work:
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
            except TimeoutError:
                continue
    logger.info("worker_loop_stopped worker_number=%d", worker_number)


async def _heartbeat_loop(
    heartbeat: WorkerHeartbeat,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            await heartbeat.refresh()
        except RedisError as exc:
            logger.warning(
                "worker_heartbeat_failed",
                extra={"error_type": type(exc).__name__},
            )
        try:
            await asyncio.wait_for(
                stop_event.wait(), timeout=WORKER_HEARTBEAT_INTERVAL_SECONDS
            )
        except TimeoutError:
            continue


async def run_worker(
    poll_seconds: float = 1,
    *,
    concurrency: int | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run bounded worker slots and stop claiming on SIGINT/SIGTERM."""
    if poll_seconds < 0:
        raise ValueError("poll_seconds cannot be negative")
    worker_count = settings.worker_concurrency if concurrency is None else concurrency
    if worker_count < 1 or worker_count > 32:
        raise ValueError("worker concurrency must be between 1 and 32")
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
    provider_error = provider_configuration_error()
    logger.info(
        "worker_ai_provider_configuration configured=%s error_code=%s timeout_seconds=%d max_attempts=%d streaming=%s",
        provider_error is None,
        provider_error.code if provider_error else None,
        settings.ai_provider_timeout_seconds,
        settings.ai_provider_max_attempts,
        settings.widget_ai_streaming_enabled,
    )
    stop = stop_event or asyncio.Event()
    loop = asyncio.get_running_loop()
    installed_signals: list[signal.Signals] = []
    if stop_event is None:
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signal_number, stop.set)
                installed_signals.append(signal_number)
            except (NotImplementedError, RuntimeError):
                continue
    dispatcher = WorkerDispatcher(job_timeout_seconds=settings.worker_job_timeout_seconds)
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    heartbeat = WorkerHeartbeat(redis_client)
    logger.info(
        "worker_runtime_started",
        extra={
            "concurrency": worker_count,
            "job_timeout_seconds": settings.worker_job_timeout_seconds,
            "poll_seconds": poll_seconds,
        },
    )
    try:
        async with asyncio.TaskGroup() as task_group:
            task_group.create_task(_heartbeat_loop(heartbeat, stop))
            for worker_number in range(worker_count):
                task_group.create_task(
                    _worker_loop(worker_number + 1, dispatcher, stop, poll_seconds)
                )
            await stop.wait()
    finally:
        for signal_number in installed_signals:
            loop.remove_signal_handler(signal_number)
        try:
            await heartbeat.stop()
        except RedisError as exc:
            logger.warning(
                "worker_heartbeat_cleanup_failed",
                extra={"error_type": type(exc).__name__},
            )
        await redis_client.aclose()
        logger.info("worker_runtime_stopped in_flight_jobs_drained=true")
