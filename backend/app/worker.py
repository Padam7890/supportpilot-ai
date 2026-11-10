"""Compatibility entry point for the modular PostgreSQL-backed worker runtime."""

import asyncio

from app.workers.application.dispatcher import WorkerDispatcher
from app.workers.handlers.ingestion import (
    LEASE_TIMEOUT,
    MAX_UPLOAD_BYTES,
    claim_one,
    extract_text,
    fail_exhausted_leases,
    process_job,
)
from app.workers.runtime import run_worker

__all__ = [
    "LEASE_TIMEOUT",
    "MAX_UPLOAD_BYTES",
    "claim_one",
    "extract_text",
    "fail_exhausted_leases",
    "process_job",
    "process_next_job",
    "run_worker",
]

_dispatcher = WorkerDispatcher()


async def process_next_job() -> bool:
    """Compatibility shim; dispatch one persisted job across registered handlers."""
    return await _dispatcher.dispatch_one()


if __name__ == "__main__":
    asyncio.run(run_worker())
