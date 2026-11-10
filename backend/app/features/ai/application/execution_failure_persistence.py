"""Tenant-scoped durable failure transitions for AI executions."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.execution_failure_policy import decide_execution_retry
from app.models import AIExecution


@dataclass(frozen=True)
class FailureTransition:
    found: bool
    attempt_count: int = 0
    max_attempts: int = 0
    reason: str | None = None
    widget_needs_fallback: bool = False


async def persist_execution_failure(
    organization_id: UUID,
    execution_id: UUID,
    *,
    retryable: bool,
    failure_code: str,
    now: datetime,
) -> FailureTransition:
    """Lock the running job and either queue retry, fail, or defer to widget handoff."""
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
            return FailureTransition(found=False)
        decision = decide_execution_retry(
            retryable=retryable,
            attempt_count=row.attempt_count,
            max_attempts=row.max_attempts,
            execution_kind=row.kind,
        )
        result = FailureTransition(
            found=True,
            attempt_count=row.attempt_count,
            max_attempts=row.max_attempts,
            reason=decision.reason,
            widget_needs_fallback=decision.widget_needs_fallback,
        )
        if decision.widget_needs_fallback:
            await db.rollback()
            return result
        row.status = "failed" if decision.exhausted else "queued"
        if row.kind == "widget_reply":
            row.reply_status = "failed" if decision.exhausted else "processing"
        if decision.exhausted:
            row.integration_context_encrypted = None
            row.playground_history = None
        row.error_code = failure_code
        row.safe_summary = (
            "The AI request could not be completed. You can create a new request."
            if decision.exhausted else None
        )
        if not decision.exhausted:
            row.next_attempt_at = now + timedelta(seconds=decision.delay_seconds)
        row.completed_at = now if decision.exhausted else None
        await db.commit()
        return result
