"""Tenant-isolated LangGraph Postgres checkpoint lifecycle."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from sqlalchemy.engine import make_url

from app.core.config import settings

CHECKPOINT_SCHEMA = "supportpilot_checkpoints"
CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")
CHECKPOINT_SETUP_LOCK = 731926405182617


def checkpoint_dsn() -> str:
    """Keep the persisted Postgres saver driver and checkpoint schema stable."""
    url = make_url(settings.database_url)
    drivername = "postgresql" if url.drivername.startswith("postgresql+") else url.drivername
    return url.set(drivername=drivername).render_as_string(hide_password=False)


@asynccontextmanager
async def tenant_checkpointer(organization_id: UUID) -> AsyncIterator[Any]:
    os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    async with AsyncPostgresSaver.from_conn_string(checkpoint_dsn()) as saver:
        await saver.conn.execute(f"SET search_path TO {CHECKPOINT_SCHEMA}")
        await saver.conn.execute("SELECT pg_advisory_lock(%s)", (CHECKPOINT_SETUP_LOCK,))
        try:
            await saver.setup()
            for table in CHECKPOINT_TABLES:
                await saver.conn.execute(
                    f"ALTER TABLE {CHECKPOINT_SCHEMA}.{table} ENABLE ROW LEVEL SECURITY"
                )
                await saver.conn.execute(
                    f"ALTER TABLE {CHECKPOINT_SCHEMA}.{table} FORCE ROW LEVEL SECURITY"
                )
                policy = await saver.conn.execute(
                    """SELECT 1 FROM pg_policies
                    WHERE schemaname = %s AND tablename = %s AND policyname = 'tenant_isolation'""",
                    (CHECKPOINT_SCHEMA, table),
                )
                if await policy.fetchone() is None:
                    await saver.conn.execute(
                        f"""CREATE POLICY tenant_isolation ON {CHECKPOINT_SCHEMA}.{table}
                        USING (split_part(thread_id, ':', 1) = NULLIF(current_setting('app.current_tenant', true), ''))
                        WITH CHECK (split_part(thread_id, ':', 1) = NULLIF(current_setting('app.current_tenant', true), ''))"""
                    )
        finally:
            await saver.conn.execute("SELECT pg_advisory_unlock(%s)", (CHECKPOINT_SETUP_LOCK,))
        await saver.conn.execute(
            "SELECT set_config('app.current_tenant', %s, false)", (str(organization_id),)
        )
        yield saver
