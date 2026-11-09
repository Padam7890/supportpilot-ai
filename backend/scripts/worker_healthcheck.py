"""Compose healthcheck: exit 0 when Redis shows at least one recent worker heartbeat."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from redis.asyncio import Redis


async def _run() -> int:
    from app.workers.application.heartbeat import active_worker_count

    url = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
    client = Redis.from_url(url, decode_responses=True)
    try:
        n = await active_worker_count(client)
    finally:
        await client.aclose()
    return 0 if n > 0 else 1


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    # Compose invokes this script by path, so Python starts in /app/scripts.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
