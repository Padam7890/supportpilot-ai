"""Durable AI execution lifecycle operations.

All database access is tenant-scoped; claim uses skip-locked leases,
and terminal transitions lock and verify the active execution state.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.db.session import SessionLocal, set_tenant_context
from app.models import AIExecution
from app.workers.domain.lease_policy import AI_EXECUTION_LEASE as LEASE_TIMEOUT


async def claim_ai_execution(organization_id: UUID) -> UUID | None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.organization_id == organization_id,
                AIExecution.attempt_count < AIExecution.max_attempts,
                or_(
                    and_(AIExecution.status == "queued", AIExecution.next_attempt_at <= now),
                    and_(
                        AIExecution.status == "running",
                        AIExecution.updated_at <= now - LEASE_TIMEOUT,
                    ),
                ),
            )
            .order_by(AIExecution.created_at, AIExecution.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if execution is None:
            await db.rollback()
            return None
        execution.status = "running"
        execution.attempt_count += 1
        execution.started_at = now
        execution.error_code = None
        execution_id = execution.id
        await db.commit()
        return execution_id


async def fail_exhausted_ai_leases(organization_id: UUID) -> bool:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.organization_id == organization_id,
                AIExecution.status == "running",
                AIExecution.attempt_count >= AIExecution.max_attempts,
                AIExecution.updated_at <= now - LEASE_TIMEOUT,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if execution is None:
            await db.rollback()
            return False
        execution.status = "failed"
        execution.integration_context_encrypted = None
        execution.playground_history = None
        execution.error_code = "worker_lease_expired"
        if execution.kind == "widget_reply":
            execution.reply_status = "failed"
        execution.safe_summary = (
            "The AI request could not be completed. You can create a new request."
        )
        execution.completed_at = now
        await db.commit()
        return True


async def finish_deterministic_ai_execution(
    organization_id: UUID,
    execution_id: UUID,
    *,
    draft: str,
    safe_summary: str,
    tool_name: str,
    result_count: int,
) -> None:
    """Persist a deterministic AI result without retaining private request context."""
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        row = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.id == execution_id,
                AIExecution.organization_id == organization_id,
                AIExecution.status == "running",
            )
            .with_for_update()
        )
        if row is None:
            await db.rollback()
            return
        row.status = "succeeded"
        row.integration_context_encrypted = None
        row.playground_history = None
        row.draft = draft
        row.safe_summary = safe_summary
        row.citations = []
        row.tool_outcomes = [
            {"tool": tool_name, "status": "completed", "result_count": result_count}
        ]
        row.usage = {}
        row.model_name = None
        row.error_code = None
        row.completed_at = now
        await db.commit()


