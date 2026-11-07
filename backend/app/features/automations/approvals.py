"""Expiration and transition helpers for durable automation approvals."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AutomationExecution,
    AutomationExecutionApproval,
    TicketActivity,
)
from app.models.automation import APPROVAL_REVIEW_WINDOW

APPROVAL_EXPIRY_BATCH_SIZE = 100


def expire_approval(
    approval: AutomationExecutionApproval,
    execution: AutomationExecution,
    *,
    now: datetime,
) -> None:
    """Set one locked pending approval and its paused execution to expired."""
    approval.status = "expired"
    execution.status = "expired"
    execution.error_code = "automation_approval_expired"
    execution.locked_until = None
    execution.lease_token = None
    execution.completed_at = now
    execution.result = [
        *execution.result,
        {
            "action_index": approval.action_index,
            "action": "require_human_approval",
            "outcome": "expired",
            "detail": f"The approval was not reviewed within {APPROVAL_REVIEW_WINDOW.days} days",
        },
    ]


async def expire_pending_automation_approvals(
    db: AsyncSession,
    organization_id: UUID,
    *,
    now: datetime | None = None,
    limit: int = APPROVAL_EXPIRY_BATCH_SIZE,
) -> int:
    """Expire a bounded batch of unattended approval steps under row locks."""
    current_time = now or datetime.now(UTC)
    has_expired_pending_approval = exists(
        select(AutomationExecutionApproval.id).where(
            AutomationExecutionApproval.organization_id == organization_id,
            AutomationExecutionApproval.execution_id == AutomationExecution.id,
            AutomationExecutionApproval.status == "pending",
            AutomationExecutionApproval.expires_at <= current_time,
        )
    )
    executions = list(
        await db.scalars(
            select(AutomationExecution)
            .where(
                AutomationExecution.organization_id == organization_id,
                AutomationExecution.status == "waiting_approval",
                has_expired_pending_approval,
            )
            .order_by(AutomationExecution.created_at, AutomationExecution.id)
            .with_for_update(skip_locked=True)
            .limit(max(1, min(limit, APPROVAL_EXPIRY_BATCH_SIZE)))
        )
    )

    expired_count = 0
    for execution in executions:
        approval = await db.scalar(
            select(AutomationExecutionApproval)
            .where(
                AutomationExecutionApproval.organization_id == organization_id,
                AutomationExecutionApproval.execution_id == execution.id,
                AutomationExecutionApproval.status == "pending",
                AutomationExecutionApproval.expires_at <= current_time,
            )
            .order_by(AutomationExecutionApproval.action_index)
            .with_for_update()
            .limit(1)
        )
        if approval is None or execution.status != "waiting_approval":
            continue
        expire_approval(approval, execution, now=current_time)
        db.add(
            TicketActivity(
                organization_id=organization_id,
                ticket_id=execution.ticket_id,
                actor_user_id=None,
                activity_type="automation_approval_expired",
                details={
                    "workflow_id": str(execution.workflow_id),
                    "execution_id": str(execution.id),
                    "approval_id": str(approval.id),
                    "action_index": approval.action_index,
                },
            )
        )
        expired_count += 1
    return expired_count
