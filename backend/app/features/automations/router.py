"""Tenant-scoped workflow configuration and execution history APIs."""

import logging
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.features.automations.contracts import (
    AutomationErrorCountOut,
    AutomationApprovalQueueItem,
    AutomationExecutionOut,
    AutomationMetricsDayOut,
    AutomationMetricsOut,
    AutomationPreviewOut,
    AutomationPreviewRequest,
    AutomationTemplateOut,
    WorkflowCanvasLayout,
    WorkflowCreate,
    WorkflowDefinition,
    WorkflowOut,
    WorkflowRestoreOut,
    WorkflowUpdate,
    WorkflowVersionHistoryOut,
    WorkflowVersionOut,
    WorkflowTemplateCreate,
    default_canvas_layout,
)
from app.features.automations.capabilities import missing_capabilities, organization_capabilities
from app.features.automations.approvals import (
    expire_approval,
    expire_pending_automation_approvals,
)
from app.features.automations.policy import preview_definition
from app.features.automations.service import (
    validate_assignment_targets,
    validate_team_assignment_targets,
    validate_definition_targets,
)
from app.features.automations.template_catalog import get_template, list_templates, materialize_template
from app.models import (
    AutomationExecution,
    AutomationExecutionApproval,
    AutomationWorkflow,
    AutomationWorkflowVersion,
    Ticket,
    TicketActivity,
    User,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/automations", tags=["automations"])
MAX_TOTAL_EXECUTION_ATTEMPTS = 5


def _definition_from_row(draft_definition: dict) -> WorkflowDefinition:
    return WorkflowDefinition.model_validate(draft_definition)


def _canvas_layout_for_workflow(draft_definition: dict, draft_canvas_layout: dict | None) -> WorkflowCanvasLayout:
    definition = _definition_from_row(draft_definition)
    if draft_canvas_layout is not None:
        return WorkflowCanvasLayout.model_validate(draft_canvas_layout)
    return default_canvas_layout(
        len(definition.conditions),
        len(definition.actions),
    )


def workflow_output(workflow: AutomationWorkflow) -> WorkflowOut:
    definition = _definition_from_row(workflow.draft_definition)
    return WorkflowOut(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        status=workflow.status,
        published_version=workflow.published_version,
        draft_version=workflow.draft_version,
        has_unpublished_changes=(
            workflow.published_version is None
            or workflow.draft_version > workflow.published_version
        ),
        definition=definition,
        canvas_layout=_canvas_layout_for_workflow(workflow.draft_definition, workflow.draft_canvas_layout),
    )


def _workflow_out_or_skip_invalid(workflow: AutomationWorkflow) -> WorkflowOut | None:
    """Build API output for a workflow row; return None if stored JSON fails schema validation."""
    try:
        return workflow_output(workflow)
    except ValidationError as exc:
        logger.warning(
            "automation_workflow_list_skip_invalid_draft",
            extra={"workflow_id": str(workflow.id), "errors": exc.errors()},
        )
        return None


@router.get("/approvals", response_model=list[AutomationApprovalQueueItem])
async def list_pending_automation_approvals(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> list[AutomationApprovalQueueItem]:
    await expire_pending_automation_approvals(db, user.organization_id)
    rows = await db.execute(
        select(AutomationExecutionApproval, AutomationExecution, AutomationWorkflow, Ticket)
        .join(
            AutomationExecution,
            (AutomationExecution.organization_id == AutomationExecutionApproval.organization_id)
            & (AutomationExecution.id == AutomationExecutionApproval.execution_id),
        )
        .join(
            AutomationWorkflow,
            (AutomationWorkflow.organization_id == AutomationExecution.organization_id)
            & (AutomationWorkflow.id == AutomationExecution.workflow_id),
        )
        .join(
            Ticket,
            (Ticket.organization_id == AutomationExecution.organization_id)
            & (Ticket.id == AutomationExecution.ticket_id),
        )
        .where(
            AutomationExecutionApproval.organization_id == user.organization_id,
            AutomationExecutionApproval.status == "pending",
            AutomationExecution.status == "waiting_approval",
        )
        .order_by(AutomationExecutionApproval.created_at, AutomationExecutionApproval.id)
        .limit(limit)
    )
    return [
        AutomationApprovalQueueItem(
            id=approval.id,
            workflow_id=execution.workflow_id,
            workflow_name=workflow.name,
            execution_id=execution.id,
            ticket_id=ticket.id,
            ticket_subject=ticket.subject,
            conversation_id=execution.conversation_id,
            action_index=approval.action_index,
            summary=approval.summary,
            detail=approval.detail,
            created_at=approval.created_at,
            expires_at=approval.expires_at,
        )
        for approval, execution, workflow, ticket in rows.all()
    ]


async def _decide_execution_approval(
    workflow_id: UUID,
    execution_id: UUID,
    action_index: int,
    *,
    decision: str,
    db: AsyncSession,
    user: User,
) -> AutomationExecutionOut:
    workflow = await _get_workflow(db, user.organization_id, workflow_id)
    execution = await db.scalar(
        select(AutomationExecution)
        .where(
            AutomationExecution.organization_id == user.organization_id,
            AutomationExecution.workflow_id == workflow.id,
            AutomationExecution.id == execution_id,
        )
        .with_for_update()
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="Workflow execution not found")
    approval = await db.scalar(
        select(AutomationExecutionApproval)
        .where(
            AutomationExecutionApproval.organization_id == user.organization_id,
            AutomationExecutionApproval.execution_id == execution.id,
            AutomationExecutionApproval.action_index == action_index,
        )
        .with_for_update()
    )
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval step not found")
    if approval.status != "pending":
        if approval.status == decision:
            version = await db.scalar(select(AutomationWorkflowVersion.version).where(
                AutomationWorkflowVersion.organization_id == user.organization_id,
                AutomationWorkflowVersion.id == execution.version_id,
            ))
            if version is None:
                raise HTTPException(status_code=409, detail="Published workflow version is unavailable")
            return execution_output(execution, version)
        raise HTTPException(status_code=409, detail="This approval already has a different decision")
    now = datetime.now(UTC)
    if approval.expires_at <= now:
        expire_approval(approval, execution, now=now)
        db.add(TicketActivity(
            organization_id=user.organization_id,
            ticket_id=execution.ticket_id,
            actor_user_id=None,
            activity_type="automation_approval_expired",
            details={
                "workflow_id": str(workflow.id),
                "execution_id": str(execution.id),
                "approval_id": str(approval.id),
                "action_index": action_index,
            },
        ))
        version = await db.scalar(select(AutomationWorkflowVersion.version).where(
            AutomationWorkflowVersion.organization_id == user.organization_id,
            AutomationWorkflowVersion.id == execution.version_id,
        ))
        if version is None:
            raise HTTPException(status_code=409, detail="Published workflow version is unavailable")
        await db.flush()
        return execution_output(execution, version)
    if execution.status != "waiting_approval":
        raise HTTPException(status_code=409, detail="Execution is no longer waiting for approval")

    approval.status = decision
    approval.reviewed_by_user_id = user.id
    approval.reviewed_at = now
    if decision == "approved":
        execution.status = "queued"
        execution.next_attempt_at = now
        execution.locked_until = None
        execution.lease_token = None
        execution.completed_at = None
        execution.error_code = None
        activity_type = "automation_approval_approved"
    else:
        execution.status = "rejected"
        execution.locked_until = None
        execution.lease_token = None
        execution.completed_at = now
        execution.result = [
            item for item in execution.result
            if item.get("action_index") != action_index
        ] + [{
            "action_index": action_index,
            "action": "require_human_approval",
            "outcome": "rejected",
            "detail": "Rejected by a workspace Owner/Admin",
        }]
        activity_type = "automation_approval_rejected"
    db.add(TicketActivity(
        organization_id=user.organization_id,
        ticket_id=execution.ticket_id,
        actor_user_id=user.id,
        activity_type=activity_type,
        details={
            "workflow_id": str(workflow.id),
            "execution_id": str(execution.id),
            "approval_id": str(approval.id),
            "action_index": action_index,
        },
    ))
    version = await db.scalar(select(AutomationWorkflowVersion.version).where(
        AutomationWorkflowVersion.organization_id == user.organization_id,
        AutomationWorkflowVersion.id == execution.version_id,
    ))
    if version is None:
        raise HTTPException(status_code=409, detail="Published workflow version is unavailable")
    await db.flush()
    return execution_output(execution, version)


@router.post("/{workflow_id}/executions/{execution_id}/approvals/{action_index}/approve", response_model=AutomationExecutionOut)
async def approve_execution_step(
    workflow_id: UUID,
    execution_id: UUID,
    action_index: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AutomationExecutionOut:
    return await _decide_execution_approval(
        workflow_id, execution_id, action_index, decision="approved", db=db, user=user
    )


@router.post("/{workflow_id}/executions/{execution_id}/approvals/{action_index}/reject", response_model=AutomationExecutionOut)
async def reject_execution_step(
    workflow_id: UUID,
    execution_id: UUID,
    action_index: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AutomationExecutionOut:
    return await _decide_execution_approval(
        workflow_id, execution_id, action_index, decision="rejected", db=db, user=user
    )


def execution_output(execution: AutomationExecution, version: int) -> AutomationExecutionOut:
    return AutomationExecutionOut(
        id=execution.id,
        workflow_id=execution.workflow_id,
        version=version,
        conversation_id=execution.conversation_id,
        ticket_id=execution.ticket_id,
        status=execution.status,
        attempt_count=execution.attempt_count,
        retry_available=(
            execution.status == "failed"
            and execution.attempt_count < MAX_TOTAL_EXECUTION_ATTEMPTS
        ),
        correlation_id=execution.correlation_id,
        result=execution.result,
        error_code=execution.error_code,
        created_at=execution.created_at,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
    )


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WorkflowOut]:
    rows = await db.scalars(
        select(AutomationWorkflow)
        .where(AutomationWorkflow.organization_id == user.organization_id)
        .order_by(AutomationWorkflow.updated_at.desc(), AutomationWorkflow.id)
        .limit(100)
    )
    return [out for row in rows if (out := _workflow_out_or_skip_invalid(row)) is not None]


@router.get("/templates", response_model=list[AutomationTemplateOut])
async def list_automation_templates(
    category: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AutomationTemplateOut]:
    caps = await organization_capabilities(db, user.organization_id)
    rows = list_templates(category=category, available_capabilities=caps)
    return [AutomationTemplateOut(**row) for row in rows]


@router.post("/workflows/from-template", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow_from_template(
    payload: WorkflowTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WorkflowOut:
    meta = get_template(payload.template_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Template not found")
    caps = await organization_capabilities(db, user.organization_id)
    missing = missing_capabilities(meta["required_capabilities"], available=caps)
    if missing:
        raise HTTPException(
            status_code=409,
            detail=f"This workspace is missing capabilities required by this template: {', '.join(missing)}",
        )
    try:
        definition, layout_raw = materialize_template(template_id=payload.template_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        await validate_assignment_targets(db, user.organization_id, definition)
        await validate_definition_targets(db, user.organization_id, definition)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    existing_count = await db.scalar(
        select(func.count(AutomationWorkflow.id)).where(
            AutomationWorkflow.organization_id == user.organization_id
        )
    )
    if int(existing_count or 0) >= 100:
        raise HTTPException(status_code=409, detail="This workspace has reached the 100 workflow limit")
    name = payload.name.strip() if payload.name else meta["title"]
    description = payload.description if payload.description is not None else meta["description"]
    if payload.canvas_layout is not None:
        if len(payload.canvas_layout.conditions) != len(definition.conditions):
            raise HTTPException(status_code=422, detail="Canvas layout must include one position for each condition")
        if len(payload.canvas_layout.actions) != len(definition.actions):
            raise HTTPException(status_code=422, detail="Canvas layout must include one position for each action")
        canvas = payload.canvas_layout.model_dump(mode="json")
    else:
        canvas = layout_raw
    workflow = AutomationWorkflow(
        organization_id=user.organization_id,
        created_by_user_id=user.id,
        name=name,
        description=description,
        draft_definition=definition.model_dump(mode="json"),
        draft_canvas_layout=canvas,
    )
    db.add(workflow)
    await db.flush()
    return workflow_output(workflow)


@router.get("/metrics", response_model=AutomationMetricsOut)
async def automation_metrics(
    days: int = Query(default=30, ge=1, le=90),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AutomationMetricsOut:
    if start_date is not None or end_date is not None:
        selected_end = end_date or datetime.now(UTC).date()
        selected_start = start_date or selected_end - timedelta(days=29)
        if selected_start > selected_end:
            raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
        if (selected_end - selected_start).days > 365:
            raise HTTPException(status_code=422, detail="Date range cannot exceed 366 days")
        window_start = datetime.combine(selected_start, time.min, tzinfo=UTC)
        window_end = datetime.combine(selected_end + timedelta(days=1), time.min, tzinfo=UTC)
    else:
        window_end = datetime.now(UTC)
        window_start = window_end - timedelta(days=days)
    counts = await db.execute(
        select(
            func.count(AutomationExecution.id),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "queued"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "running"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "succeeded"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "failed"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "expired"),
            func.avg(
                func.extract("epoch", AutomationExecution.completed_at - AutomationExecution.started_at)
            ).filter(
                AutomationExecution.status == "succeeded",
                AutomationExecution.started_at.is_not(None),
                AutomationExecution.completed_at.is_not(None),
            ),
        ).where(
            AutomationExecution.organization_id == user.organization_id,
            AutomationExecution.created_at >= window_start,
            AutomationExecution.created_at < window_end,
        )
    )
    total, queued, running, succeeded, failed, expired, average_seconds = counts.one()
    day_bucket = cast(func.timezone("UTC", AutomationExecution.created_at), Date).label("day")
    daily_rows = await db.execute(
        select(
            day_bucket,
            func.count(AutomationExecution.id),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "succeeded"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "failed"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "expired"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "queued"),
            func.count(AutomationExecution.id).filter(AutomationExecution.status == "running"),
        )
        .where(
            AutomationExecution.organization_id == user.organization_id,
            AutomationExecution.created_at >= window_start,
            AutomationExecution.created_at < window_end,
        )
        .group_by(day_bucket)
    )
    daily_by_date = {
        row[0]: row[1:] for row in daily_rows.all()
    }
    first_day = window_start.date()
    last_day = (window_end - timedelta(microseconds=1)).date()
    daily = []
    for offset in range((last_day - first_day).days + 1):
        day = first_day + timedelta(days=offset)
        values = daily_by_date.get(day, (0, 0, 0, 0, 0, 0))
        daily.append(
            AutomationMetricsDayOut(
                date=day,
                total=int(values[0]),
                succeeded=int(values[1]),
                failed=int(values[2]),
                expired=int(values[3]),
                queued=int(values[4]),
                running=int(values[5]),
            )
        )
    errors_rows = await db.execute(
        select(
            func.coalesce(AutomationExecution.error_code, "unknown"),
            func.count(AutomationExecution.id),
        )
        .where(
            AutomationExecution.organization_id == user.organization_id,
            AutomationExecution.created_at >= window_start,
            AutomationExecution.created_at < window_end,
            AutomationExecution.status == "failed",
        )
        .group_by(AutomationExecution.error_code)
        .order_by(func.count(AutomationExecution.id).desc(), AutomationExecution.error_code)
        .limit(5)
    )
    top_errors = [
        AutomationErrorCountOut(code=str(code), count=int(count))
        for code, count in errors_rows.all()
    ]
    return AutomationMetricsOut(
        window_start=window_start,
        window_end=window_end,
        total=int(total),
        queued=int(queued),
        running=int(running),
        succeeded=int(succeeded),
        failed=int(failed),
        expired=int(expired),
        average_duration_ms=round(float(average_seconds) * 1000) if average_seconds is not None else None,
        daily=daily,
        top_errors=top_errors,
    )


@router.post("/preview", response_model=AutomationPreviewOut)
async def preview_automation(
    payload: AutomationPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AutomationPreviewOut:
    """Evaluate a sample message and proposed actions without changing ticket data."""
    try:
        await validate_assignment_targets(db, user.organization_id, payload.definition)
        await validate_team_assignment_targets(db, user.organization_id, payload.definition)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return preview_definition(
        payload.definition,
        message=payload.sample_message,
        current_ticket_priority=payload.sample_ticket_priority,
        current_ticket_status=payload.sample_ticket_status,
        channel=payload.sample_channel,
        is_first_customer_message=payload.sample_is_first_customer_message,
        assignee_present=payload.sample_assignee_present,
        conversation_ai_mode=payload.sample_conversation_ai_mode,
        shopify_connected=payload.sample_shopify_connected,
    )


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: WorkflowCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WorkflowOut:
    existing_count = await db.scalar(
        select(func.count(AutomationWorkflow.id)).where(
            AutomationWorkflow.organization_id == user.organization_id
        )
    )
    if int(existing_count or 0) >= 100:
        raise HTTPException(status_code=409, detail="This workspace has reached the 100 workflow limit")
    workflow = AutomationWorkflow(
        organization_id=user.organization_id,
        created_by_user_id=user.id,
        name=payload.name.strip(),
        description=payload.description,
        draft_definition=payload.definition.model_dump(mode="json"),
        draft_canvas_layout=(
            payload.canvas_layout
            or default_canvas_layout(len(payload.definition.conditions), len(payload.definition.actions))
        ).model_dump(mode="json"),
    )
    db.add(workflow)
    await db.flush()
    return workflow_output(workflow)


@router.get("/{workflow_id}", response_model=WorkflowOut)
async def get_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkflowOut:
    workflow = await _get_workflow(db, user.organization_id, workflow_id)
    return workflow_output(workflow)


@router.patch("/{workflow_id}", response_model=WorkflowOut)
async def update_workflow(
    workflow_id: UUID,
    payload: WorkflowUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WorkflowOut:
    workflow = await _get_workflow(db, user.organization_id, workflow_id, lock=True)
    supplied = payload.model_fields_set
    if "name" in supplied and payload.name is not None:
        workflow.name = payload.name.strip()
    if "description" in supplied:
        workflow.description = payload.description
    next_definition = payload.definition or WorkflowDefinition.model_validate(workflow.draft_definition)
    if payload.definition is not None:
        workflow.draft_definition = payload.definition.model_dump(mode="json")
        if workflow.published_version is not None and workflow.draft_version <= workflow.published_version:
            workflow.draft_version = workflow.published_version + 1
    if "canvas_layout" in supplied:
        layout = payload.canvas_layout or default_canvas_layout(
            len(next_definition.conditions), len(next_definition.actions)
        )
        if len(layout.conditions) != len(next_definition.conditions):
            raise HTTPException(status_code=422, detail="Canvas layout must include one position for each condition")
        if len(layout.actions) != len(next_definition.actions):
            raise HTTPException(status_code=422, detail="Canvas layout must include one position for each action")
        workflow.draft_canvas_layout = layout.model_dump(mode="json")
    elif payload.definition is not None:
        current_layout = (
            WorkflowCanvasLayout.model_validate(workflow.draft_canvas_layout)
            if workflow.draft_canvas_layout is not None
            else None
        )
        if (
            current_layout is None
            or len(current_layout.conditions) != len(next_definition.conditions)
            or len(current_layout.actions) != len(next_definition.actions)
        ):
            workflow.draft_canvas_layout = default_canvas_layout(
                len(next_definition.conditions), len(next_definition.actions)
            ).model_dump(mode="json")
    await db.flush()
    return workflow_output(workflow)


@router.post("/{workflow_id}/publish", response_model=WorkflowVersionOut)
async def publish_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WorkflowVersionOut:
    workflow = await _get_workflow(db, user.organization_id, workflow_id, lock=True)
    definition = WorkflowDefinition.model_validate(workflow.draft_definition)
    try:
        await validate_definition_targets(db, user.organization_id, definition)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    version = workflow.draft_version
    if workflow.published_version is not None and version <= workflow.published_version:
        raise HTTPException(status_code=409, detail="There are no unpublished workflow changes")
    published = AutomationWorkflowVersion(
        organization_id=user.organization_id,
        workflow_id=workflow.id,
        version=version,
        definition=definition.model_dump(mode="json"),
        canvas_layout=(
            WorkflowCanvasLayout.model_validate(workflow.draft_canvas_layout)
            if workflow.draft_canvas_layout is not None
            else default_canvas_layout(len(definition.conditions), len(definition.actions))
        ).model_dump(mode="json"),
        published_by_user_id=user.id,
    )
    db.add(published)
    workflow.published_version = version
    workflow.status = "active"
    await db.flush()
    return WorkflowVersionOut(workflow_id=workflow.id, version=version, status=workflow.status)


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionHistoryOut])
async def list_workflow_versions(
    workflow_id: UUID,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[WorkflowVersionHistoryOut]:
    workflow = await _get_workflow(db, user.organization_id, workflow_id)
    if not 1 <= limit <= 100:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 100")
    versions = await db.scalars(
        select(AutomationWorkflowVersion)
        .where(
            AutomationWorkflowVersion.organization_id == user.organization_id,
            AutomationWorkflowVersion.workflow_id == workflow.id,
        )
        .order_by(AutomationWorkflowVersion.version.desc())
        .limit(limit)
    )
    return [
        WorkflowVersionHistoryOut(
            workflow_id=workflow.id,
            version=version.version,
            created_at=version.created_at,
            is_current=version.version == workflow.published_version,
        )
        for version in versions
    ]


@router.post(
    "/{workflow_id}/versions/{version}/restore",
    response_model=WorkflowRestoreOut,
)
async def restore_workflow_version(
    workflow_id: UUID,
    version: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WorkflowRestoreOut:
    workflow = await _get_workflow(db, user.organization_id, workflow_id, lock=True)
    source = await db.scalar(
        select(AutomationWorkflowVersion).where(
            AutomationWorkflowVersion.organization_id == user.organization_id,
            AutomationWorkflowVersion.workflow_id == workflow.id,
            AutomationWorkflowVersion.version == version,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Published workflow version not found")
    definition = WorkflowDefinition.model_validate(source.definition)
    try:
        await validate_definition_targets(db, user.organization_id, definition)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    workflow.draft_definition = definition.model_dump(mode="json")
    workflow.draft_canvas_layout = (
        WorkflowCanvasLayout.model_validate(source.canvas_layout)
        if source.canvas_layout is not None
        else default_canvas_layout(len(definition.conditions), len(definition.actions))
    ).model_dump(mode="json")
    workflow.draft_version = max(workflow.draft_version, workflow.published_version or 0) + 1
    await db.flush()
    return WorkflowRestoreOut(
        workflow=workflow_output(workflow),
        restored_from_version=source.version,
        message="Restored as a new draft. Review and publish it to make it active.",
    )


@router.post("/{workflow_id}/pause", response_model=WorkflowOut)
async def pause_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WorkflowOut:
    workflow = await _get_workflow(db, user.organization_id, workflow_id, lock=True)
    workflow.status = "paused"
    await db.flush()
    return workflow_output(workflow)


@router.post("/{workflow_id}/resume", response_model=WorkflowOut)
async def resume_workflow(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WorkflowOut:
    workflow = await _get_workflow(db, user.organization_id, workflow_id, lock=True)
    if workflow.published_version is None:
        raise HTTPException(status_code=409, detail="Publish this workflow before enabling it")
    workflow.status = "active"
    await db.flush()
    return workflow_output(workflow)


@router.get("/{workflow_id}/executions", response_model=list[AutomationExecutionOut])
async def list_executions(
    workflow_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AutomationExecutionOut]:
    workflow = await _get_workflow(db, user.organization_id, workflow_id)
    rows = await db.execute(
        select(AutomationExecution, AutomationWorkflowVersion.version)
        .join(
            AutomationWorkflowVersion,
            (AutomationWorkflowVersion.organization_id == AutomationExecution.organization_id)
            & (AutomationWorkflowVersion.id == AutomationExecution.version_id),
        )
        .where(
            AutomationExecution.organization_id == user.organization_id,
            AutomationExecution.workflow_id == workflow.id,
        )
        .order_by(AutomationExecution.created_at.desc(), AutomationExecution.id)
        .limit(100)
    )
    return [execution_output(row, version) for row, version in rows.all()]


@router.post(
    "/{workflow_id}/executions/{execution_id}/retry",
    response_model=AutomationExecutionOut,
)
async def retry_execution(
    workflow_id: UUID,
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AutomationExecutionOut:
    """Manually queue one failed run again, preserving its immutable workflow version."""
    workflow = await _get_workflow(db, user.organization_id, workflow_id)
    execution = await db.scalar(
        select(AutomationExecution)
        .where(
            AutomationExecution.organization_id == user.organization_id,
            AutomationExecution.workflow_id == workflow.id,
            AutomationExecution.id == execution_id,
        )
        .with_for_update()
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="Workflow execution not found")
    if execution.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed executions can be retried")
    if execution.attempt_count >= MAX_TOTAL_EXECUTION_ATTEMPTS:
        raise HTTPException(status_code=409, detail="This execution reached its retry limit")
    version = await db.scalar(
        select(AutomationWorkflowVersion.version).where(
            AutomationWorkflowVersion.organization_id == user.organization_id,
            AutomationWorkflowVersion.id == execution.version_id,
            AutomationWorkflowVersion.workflow_id == workflow.id,
        )
    )
    if version is None:
        raise HTTPException(status_code=409, detail="The published workflow version is unavailable")

    now = datetime.now(UTC)
    execution.max_attempts = min(
        MAX_TOTAL_EXECUTION_ATTEMPTS,
        max(execution.max_attempts, execution.attempt_count + 1),
    )
    execution.status = "queued"
    execution.next_attempt_at = now
    execution.locked_until = None
    execution.lease_token = None
    execution.error_code = None
    execution.completed_at = None
    execution.result = []
    db.add(
        TicketActivity(
            organization_id=user.organization_id,
            ticket_id=execution.ticket_id,
            actor_user_id=user.id,
            activity_type="automation_retry_requested",
            details={
                "workflow_id": str(workflow.id),
                "execution_id": str(execution.id),
                "version": version,
                "attempt_count": execution.attempt_count,
                "attempt_limit": execution.max_attempts,
            },
        )
    )
    await db.flush()
    return execution_output(execution, version)


async def _get_workflow(
    db: AsyncSession, organization_id: UUID, workflow_id: UUID, *, lock: bool = False
) -> AutomationWorkflow:
    query = select(AutomationWorkflow).where(
        AutomationWorkflow.organization_id == organization_id,
        AutomationWorkflow.id == workflow_id,
    )
    if lock:
        query = query.with_for_update()
    workflow = await db.scalar(query)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow
