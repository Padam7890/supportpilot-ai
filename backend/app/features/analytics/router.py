import re
from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Integer, String, Uuid, func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models import (
    AIAgent,
    AIEvaluation,
    AIExecution,
    AutomationExecution,
    CatalogSyncJob,
    CatalogWebhookEvent,
    CommerceAction,
    Conversation,
    DocumentIngestionJob,
    IntegrationConnection,
    IntegrationDeliveryJob,
    Message,
    User,
)
from app.schemas.analytics import (
    AIEvaluationCreate,
    AIEvaluationOut,
    AIEvaluationSummaryOut,
    AIUsageDay,
    AIUsageOut,
    AIExecutionErrorCount,
    AIBotUsage,
    CommerceApprovalAnalyticsOut,
    CommerceApprovalDay,
    FailedBackgroundJobOut,
    FailedBackgroundJobsOut,
    JobTraceEventOut,
    JobTraceOut,
    IntegrationDeliveryAnalyticsOut,
    IntegrationDeliveryDay,
    IntegrationDeliveryError,
    IntegrationDeliveryProvider,
    OperationalAlertOut,
    OperationalAlertsOut,
    SupportResponseAnalyticsOut,
    SupportResponseDay,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(prefix="/analytics", tags=["analytics"], responses=COMMON_ERROR_RESPONSES)


def date_window(start_date: date | None, end_date: date | None) -> tuple[date, date]:
    end = end_date or datetime.now(UTC).date()
    start = start_date or (end - timedelta(days=29))
    if start > end:
        raise HTTPException(status_code=422, detail="start_date must be on or before end_date")
    if (end - start).days > 365:
        raise HTTPException(status_code=422, detail="Date range cannot exceed 366 days")
    return start, end


def date_predicate(column, start: date, end: date):
    lower = datetime.combine(start, time.min, tzinfo=UTC)
    upper = datetime.combine(end + timedelta(days=1), time.min, tzinfo=UTC)
    return (column >= lower) & (column < upper)


@router.get("/operational-alerts", response_model=OperationalAlertsOut)
async def operational_alerts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> OperationalAlertsOut:
    """Return actionable counts from persisted tenant jobs without exposing payloads."""
    generated_at = datetime.now(UTC)
    window_start = generated_at - timedelta(hours=24)

    def count_subquery(model, *conditions):
        return (
            select(func.count(model.id))
            .where(model.organization_id == user.organization_id, *conditions)
            .scalar_subquery()
        )
    counts = await db.execute(
        select(
            count_subquery(
                AIExecution, AIExecution.status == "failed", AIExecution.created_at >= window_start
            ),
            count_subquery(
                AutomationExecution,
                AutomationExecution.status == "failed",
                AutomationExecution.created_at >= window_start,
            ),
            count_subquery(
                CatalogSyncJob,
                CatalogSyncJob.status == "failed",
                CatalogSyncJob.created_at >= window_start,
            ),
            count_subquery(
                CatalogWebhookEvent,
                CatalogWebhookEvent.status == "failed",
                CatalogWebhookEvent.created_at >= window_start,
            ),
            count_subquery(
                IntegrationDeliveryJob,
                IntegrationDeliveryJob.status == "failed",
                IntegrationDeliveryJob.created_at >= window_start,
            ),
            count_subquery(
                DocumentIngestionJob,
                DocumentIngestionJob.status == "failed",
                DocumentIngestionJob.created_at >= window_start,
            ),
            count_subquery(
                CommerceAction,
                CommerceAction.approval_status == "pending",
                CommerceAction.expires_at > generated_at,
            ),
            count_subquery(
                CommerceAction,
                CommerceAction.execution_status == "failed",
                CommerceAction.execution_completed_at >= window_start,
            ),
        )
    )
    (
        ai_failed,
        automation_failed,
        catalog_failed,
        webhook_failed,
        delivery_failed,
        ingestion_failed,
        approvals_pending,
        commerce_failed,
    ) = counts.one()

    candidates = [
        (
            "ai_execution_failed", "attention", "AI runs failed",
            "Review recent AI executions that exhausted their retry policy.",
            int(ai_failed or 0), "Review AI activity", "/dashboard/analytics#ai-errors-title",
        ),
        (
            "automation_execution_failed", "attention", "Automation runs failed",
            "Review recent workflow executions that exhausted their retry policy.",
            int(automation_failed or 0), "Review automations", "/dashboard/automations",
        ),
        (
            "catalog_sync_failed", "attention", "Catalog syncs failed",
            "Review recent catalog synchronization jobs for this workspace.",
            int(catalog_failed or 0), "Open integrations", "/dashboard/settings#shopify",
        ),
        (
            "catalog_webhook_failed", "attention", "Catalog webhooks failed",
            "Review recent Shopify catalog events that could not be processed.",
            int(webhook_failed or 0), "Open integrations", "/dashboard/settings#shopify",
        ),
        (
            "outbound_delivery_failed", "attention", "Outbound deliveries failed",
            "Review recent channel messages that exhausted their delivery retries.",
            int(delivery_failed or 0), "View delivery analytics", "/dashboard/analytics#channel-delivery",
        ),
        (
            "document_ingestion_failed", "attention", "Knowledge documents failed to process",
            "Review recent document processing failures and retry them after checking the source file.",
            int(ingestion_failed or 0), "Open Knowledge Library", "/dashboard/knowledge",
        ),
        (
            "commerce_approval_pending", "review", "Commerce requests need review",
            "Unexpired cancellation or refund requests are waiting for an authorized reviewer.",
            int(approvals_pending or 0), "Review requests", "/dashboard/operations#commerce-actions",
        ),
        (
            "commerce_execution_failed", "attention", "Commerce actions failed",
            "Review recent approved actions whose provider execution failed.",
            int(commerce_failed or 0), "Review action history", "/dashboard/operations#commerce-actions",
        ),
    ]
    return OperationalAlertsOut(
        generated_at=generated_at,
        window_start=window_start,
        alerts=[
            OperationalAlertOut(
                code=code,
                severity=severity,
                title=title,
                description=description,
                count=count,
                action_label=action_label,
                href=href,
            )
            for code, severity, title, description, count, action_label, href in candidates
            if count > 0
        ],
    )


@router.get("/support-response-times", response_model=SupportResponseAnalyticsOut)
async def support_response_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SupportResponseAnalyticsOut:
    """Summarize first customer-to-team reply time, excluding message content."""
    start, end = date_window(start_date, end_date)
    first_customer = (
        select(
            Conversation.organization_id.label("organization_id"),
            Conversation.id.label("conversation_id"),
            func.min(Message.created_at).label("first_customer_at"),
        )
        .join(
            Message,
            (Message.organization_id == Conversation.organization_id)
            & (Message.conversation_id == Conversation.id),
        )
        .where(
            Conversation.organization_id == user.organization_id,
            date_predicate(Conversation.created_at, start, end),
            Message.sender_type == "customer",
        )
        .group_by(Conversation.organization_id, Conversation.id)
        .cte("first_customer_message")
    )
    response_messages = Message.__table__
    conversation_times = (
        select(
            first_customer.c.organization_id,
            first_customer.c.conversation_id,
            first_customer.c.first_customer_at,
            func.min(response_messages.c.created_at)
            .filter(response_messages.c.sender_type.in_(("agent", "assistant")))
            .label("first_response_at"),
        )
        .select_from(
            first_customer.outerjoin(
                response_messages,
                (response_messages.c.organization_id == first_customer.c.organization_id)
                & (response_messages.c.conversation_id == first_customer.c.conversation_id)
                & (response_messages.c.created_at > first_customer.c.first_customer_at),
            )
        )
        .group_by(
            first_customer.c.organization_id,
            first_customer.c.conversation_id,
            first_customer.c.first_customer_at,
        )
        .cte("conversation_first_responses")
    )
    latency_seconds = func.extract(
        "epoch", conversation_times.c.first_response_at - conversation_times.c.first_customer_at
    )
    summary = await db.execute(
        select(
            func.count(conversation_times.c.conversation_id),
            func.count(conversation_times.c.conversation_id).filter(
                conversation_times.c.first_response_at.is_not(None)
            ),
            func.avg(latency_seconds).filter(conversation_times.c.first_response_at.is_not(None)),
            func.percentile_disc(0.5).within_group(latency_seconds),
        )
    )
    total, responded, average_seconds, median_seconds = summary.one()

    utc_day = func.date(func.timezone("UTC", conversation_times.c.first_customer_at))
    daily_rows = await db.execute(
        select(
            utc_day,
            func.count(conversation_times.c.conversation_id),
            func.count(conversation_times.c.conversation_id).filter(
                conversation_times.c.first_response_at.is_not(None)
            ),
            func.avg(latency_seconds).filter(conversation_times.c.first_response_at.is_not(None)),
        )
        .group_by(utc_day)
        .order_by(utc_day)
    )
    daily = [
        SupportResponseDay(
            date=day,
            conversations=int(conversation_count),
            responded=int(response_count),
            average_first_response_seconds=(
                round(float(day_average), 2) if day_average is not None else None
            ),
        )
        for day, conversation_count, response_count, day_average in daily_rows.all()
    ]
    total_count = int(total or 0)
    response_count = int(responded or 0)
    return SupportResponseAnalyticsOut(
        start_date=start,
        end_date=end,
        conversations=total_count,
        responded=response_count,
        awaiting_first_response=total_count - response_count,
        average_first_response_seconds=(
            round(float(average_seconds), 2) if average_seconds is not None else None
        ),
        median_first_response_seconds=(
            round(float(median_seconds), 2) if median_seconds is not None else None
        ),
        daily=daily,
    )


@router.get("/integration-deliveries", response_model=IntegrationDeliveryAnalyticsOut)
async def integration_delivery_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IntegrationDeliveryAnalyticsOut:
    """Summarize persisted outbound jobs for this tenant without exposing message data."""
    start, end = date_window(start_date, end_date)
    scope = (
        IntegrationDeliveryJob.organization_id == user.organization_id,
        date_predicate(IntegrationDeliveryJob.created_at, start, end),
    )
    totals = await db.execute(
        select(
            func.count(IntegrationDeliveryJob.id),
            func.count(IntegrationDeliveryJob.id).filter(IntegrationDeliveryJob.status == "succeeded"),
            func.count(IntegrationDeliveryJob.id).filter(IntegrationDeliveryJob.status == "failed"),
            func.count(IntegrationDeliveryJob.id).filter(IntegrationDeliveryJob.status == "queued"),
            func.count(IntegrationDeliveryJob.id).filter(IntegrationDeliveryJob.status == "running"),
            func.count(IntegrationDeliveryJob.id).filter(IntegrationDeliveryJob.status == "cancelled"),
            func.avg(IntegrationDeliveryJob.attempt_count),
        ).where(*scope)
    )
    total, succeeded, failed, queued, running, cancelled, average_attempts = totals.one()

    provider_rows = await db.execute(
        select(
            IntegrationConnection.provider_id,
            func.count(IntegrationDeliveryJob.id),
            func.count(IntegrationDeliveryJob.id).filter(IntegrationDeliveryJob.status == "succeeded"),
            func.count(IntegrationDeliveryJob.id).filter(IntegrationDeliveryJob.status == "failed"),
        )
        .join(
            IntegrationConnection,
            (IntegrationConnection.organization_id == IntegrationDeliveryJob.organization_id)
            & (IntegrationConnection.id == IntegrationDeliveryJob.connection_id),
        )
        .where(*scope)
        .group_by(IntegrationConnection.provider_id)
        .order_by(IntegrationConnection.provider_id)
    )
    providers = [
        IntegrationDeliveryProvider(
            provider_id=provider_id,
            total=int(provider_total),
            succeeded=int(provider_succeeded),
            failed=int(provider_failed),
        )
        for provider_id, provider_total, provider_succeeded, provider_failed in provider_rows.all()
    ]

    utc_created_date = func.date(func.timezone("UTC", IntegrationDeliveryJob.created_at))
    daily_rows = await db.execute(
        select(
            utc_created_date,
            IntegrationDeliveryJob.status,
            func.count(IntegrationDeliveryJob.id),
        )
        .where(*scope)
        .group_by(utc_created_date, IntegrationDeliveryJob.status)
    )
    daily_counts: dict[date, dict[str, int]] = {}
    for day, delivery_status, count in daily_rows.all():
        daily_counts.setdefault(day, {})[delivery_status] = int(count)
    daily = [
        IntegrationDeliveryDay(
            date=day,
            total=sum(counts.values()),
            succeeded=counts.get("succeeded", 0),
            failed=counts.get("failed", 0),
            queued=counts.get("queued", 0),
            running=counts.get("running", 0),
            cancelled=counts.get("cancelled", 0),
        )
        for day, counts in sorted(daily_counts.items())
    ]
    error_rows = await db.execute(
        select(IntegrationDeliveryJob.last_error_code, func.count(IntegrationDeliveryJob.id))
        .where(*scope, IntegrationDeliveryJob.status == "failed", IntegrationDeliveryJob.last_error_code.is_not(None))
        .group_by(IntegrationDeliveryJob.last_error_code)
        .order_by(func.count(IntegrationDeliveryJob.id).desc(), IntegrationDeliveryJob.last_error_code)
        .limit(10)
    )
    return IntegrationDeliveryAnalyticsOut(
        start_date=start,
        end_date=end,
        total=int(total),
        succeeded=int(succeeded),
        failed=int(failed),
        queued=int(queued),
        running=int(running),
        cancelled=int(cancelled),
        average_attempts=round(float(average_attempts), 2) if average_attempts is not None else None,
        providers=providers,
        daily=daily,
        top_errors=[IntegrationDeliveryError(code=code, count=int(count)) for code, count in error_rows.all()],
    )


@router.get("/ai-usage", response_model=AIUsageOut)
async def ai_usage(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AIUsageOut:
    start, end = date_window(start_date, end_date)
    predicate = (
        AIExecution.organization_id == user.organization_id,
        date_predicate(AIExecution.created_at, start, end),
    )
    prompt_tokens = func.coalesce(func.sum(AIExecution.usage["prompt_tokens"].as_integer()), 0)
    completion_tokens = func.coalesce(func.sum(AIExecution.usage["completion_tokens"].as_integer()), 0)
    aggregate = await db.execute(
        select(
            func.count(AIExecution.id),
            func.count(AIExecution.id).filter(AIExecution.status == "succeeded"),
            func.count(AIExecution.id).filter(AIExecution.status == "failed"),
            prompt_tokens,
            completion_tokens,
        ).where(*predicate)
    )
    count, succeeded, failed, prompt, completion = aggregate.one()
    document_eligible = (
        AIExecution.status == "succeeded",
        AIExecution.kind.in_(("playground", "reply_draft", "widget_reply")),
        AIExecution.model_name.is_not(None),
    )
    document_grounding = await db.execute(
        select(
            func.count(AIExecution.id).filter(*document_eligible),
            func.count(AIExecution.id).filter(
                *document_eligible,
                func.json_array_length(AIExecution.citations) > 0,
            ),
        ).where(*predicate)
    )
    model_backed_responses, cited_responses = (
        int(value or 0) for value in document_grounding.one()
    )
    daily_rows = await db.execute(
        select(
            func.date(AIExecution.created_at),
            func.count(AIExecution.id),
            prompt_tokens,
            completion_tokens,
            func.count(AIExecution.id).filter(AIExecution.status == "failed"),
        )
        .where(*predicate)
        .group_by(func.date(AIExecution.created_at))
        .order_by(func.date(AIExecution.created_at))
    )
    daily_map = {
        day: (int(executions), int(day_prompt), int(day_completion), int(day_failed))
        for day, executions, day_prompt, day_completion, day_failed in daily_rows.all()
    }
    daily = [
        AIUsageDay(
            date=day,
            executions=daily_map.get(day, (0, 0, 0, 0))[0],
            prompt_tokens=daily_map.get(day, (0, 0, 0, 0))[1],
            completion_tokens=daily_map.get(day, (0, 0, 0, 0))[2],
            failed=daily_map.get(day, (0, 0, 0, 0))[3],
        )
        for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1))
    ]
    prompt, completion = int(prompt), int(completion)
    estimated_cost = None
    if settings.ai_input_cost_per_million is not None and settings.ai_output_cost_per_million is not None:
        estimated_cost = (
            prompt * settings.ai_input_cost_per_million
            + completion * settings.ai_output_cost_per_million
        ) / 1_000_000
    bot_rows = await db.execute(
        select(
            AIExecution.ai_agent_id,
            AIAgent.name,
            func.count(AIExecution.id),
            func.count(AIExecution.id).filter(AIExecution.status == "succeeded"),
            func.count(AIExecution.id).filter(AIExecution.status == "failed"),
            prompt_tokens,
            completion_tokens,
            func.avg(
                func.extract("epoch", AIExecution.completed_at - AIExecution.started_at)
            ).filter(
                AIExecution.status == "succeeded",
                AIExecution.started_at.is_not(None),
                AIExecution.completed_at.is_not(None),
            ),
        )
        .join(
            AIAgent,
            (AIAgent.organization_id == AIExecution.organization_id)
            & (AIAgent.id == AIExecution.ai_agent_id),
        )
        .where(*predicate)
        .group_by(AIExecution.ai_agent_id, AIAgent.name)
        .order_by(func.count(AIExecution.id).desc(), AIAgent.name, AIExecution.ai_agent_id)
        .limit(100)
    )
    bot_usage = []
    for (
        bot_id,
        bot_name,
        executions,
        bot_succeeded,
        bot_failed,
        bot_prompt,
        bot_completion,
        latency,
    ) in bot_rows.all():
        bot_prompt, bot_completion = int(bot_prompt or 0), int(bot_completion or 0)
        bot_cost = None
        if settings.ai_input_cost_per_million is not None and settings.ai_output_cost_per_million is not None:
            bot_cost = (
                bot_prompt * settings.ai_input_cost_per_million
                + bot_completion * settings.ai_output_cost_per_million
            ) / 1_000_000
        bot_usage.append(
            AIBotUsage(
                bot_id=bot_id,
                bot_name=bot_name,
                executions=int(executions),
                succeeded=int(bot_succeeded),
                failed=int(bot_failed),
                prompt_tokens=bot_prompt,
                completion_tokens=bot_completion,
                estimated_cost_usd=bot_cost,
                average_latency_ms=round(float(latency) * 1000) if latency is not None else None,
            )
        )
    error_rows = await db.execute(
        select(AIExecution.error_code, func.count(AIExecution.id))
        .where(
            *predicate,
            AIExecution.status == "failed",
            AIExecution.error_code.is_not(None),
        )
        .group_by(AIExecution.error_code)
        .order_by(func.count(AIExecution.id).desc(), AIExecution.error_code.asc())
        .limit(10)
    )
    return AIUsageOut(
        start_date=start,
        end_date=end,
        executions=int(count),
        succeeded=int(succeeded),
        failed=int(failed),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        estimated_cost_usd=estimated_cost,
        daily=daily,
        bots=bot_usage,
        top_errors=[
            AIExecutionErrorCount(code=code, count=int(error_count))
            for code, error_count in error_rows.all()
        ],
        model_backed_responses=model_backed_responses,
        responses_with_document_citations=cited_responses,
        document_citation_rate=(
            cited_responses / model_backed_responses if model_backed_responses else None
        ),
    )


@router.get("/commerce-approvals", response_model=CommerceApprovalAnalyticsOut)
async def commerce_approval_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CommerceApprovalAnalyticsOut:
    """Summarize tenant-owned human-reviewed commerce requests without order details."""
    start, end = date_window(start_date, end_date)
    predicate = (
        CommerceAction.organization_id == user.organization_id,
        date_predicate(CommerceAction.created_at, start, end),
    )
    totals_result = await db.execute(
        select(
            func.count(CommerceAction.id),
            func.count(CommerceAction.id).filter(CommerceAction.approval_status == "pending"),
            func.count(CommerceAction.id).filter(CommerceAction.approval_status == "approved"),
            func.count(CommerceAction.id).filter(CommerceAction.approval_status == "rejected"),
            func.count(CommerceAction.id).filter(CommerceAction.approval_status == "expired"),
            func.count(CommerceAction.id).filter(CommerceAction.approval_status == "cancelled"),
            func.count(CommerceAction.id).filter(CommerceAction.execution_status == "succeeded"),
            func.count(CommerceAction.id).filter(CommerceAction.execution_status == "failed"),
            func.avg(func.extract("epoch", CommerceAction.reviewed_at - CommerceAction.created_at)).filter(
                CommerceAction.reviewed_at.is_not(None)
            ),
        ).where(*predicate)
    )
    total, pending, approved, rejected, expired, cancelled, executed, execution_failed, review_seconds = totals_result.one()

    utc_created_date = func.date(func.timezone("UTC", CommerceAction.created_at))
    daily_rows = await db.execute(
        select(
            utc_created_date,
            CommerceAction.approval_status,
            func.count(CommerceAction.id),
        )
        .where(*predicate)
        .group_by(utc_created_date, CommerceAction.approval_status)
    )
    daily_counts: dict[date, dict[str, int]] = {}
    for day, approval_status, count in daily_rows.all():
        daily_counts.setdefault(day, {})[approval_status] = int(count)
    daily = []
    for day in (start + timedelta(days=offset) for offset in range((end - start).days + 1)):
        counts = daily_counts.get(day, {})
        daily.append(
            CommerceApprovalDay(
                date=day,
                total=sum(counts.values()),
                pending=counts.get("pending", 0),
                approved=counts.get("approved", 0),
                rejected=counts.get("rejected", 0),
                expired=counts.get("expired", 0),
                cancelled=counts.get("cancelled", 0),
            )
        )
    return CommerceApprovalAnalyticsOut(
        start_date=start,
        end_date=end,
        total=int(total),
        pending=int(pending),
        approved=int(approved),
        rejected=int(rejected),
        expired=int(expired),
        cancelled=int(cancelled),
        execution_succeeded=int(executed),
        execution_failed=int(execution_failed),
        average_review_seconds=round(float(review_seconds), 2) if review_seconds is not None else None,
        daily=daily,
    )


@router.get("/evaluations", response_model=AIEvaluationSummaryOut)
async def evaluation_summary(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AIEvaluationSummaryOut:
    start, end = date_window(start_date, end_date)
    predicate = (
        AIEvaluation.organization_id == user.organization_id,
        date_predicate(AIEvaluation.created_at, start, end),
    )
    summary = await db.execute(
        select(
            func.count(AIEvaluation.id),
            func.count(AIEvaluation.id).filter(AIEvaluation.rating == "helpful"),
            func.count(AIEvaluation.id).filter(AIEvaluation.rating == "not_helpful"),
        ).where(*predicate)
    )
    rated, helpful, not_helpful = (int(value) for value in summary.one())
    categories = await db.execute(
        select(AIEvaluation.category, func.count(AIEvaluation.id))
        .where(*predicate, AIEvaluation.category.is_not(None))
        .group_by(AIEvaluation.category)
    )
    return AIEvaluationSummaryOut(
        start_date=start,
        end_date=end,
        rated=rated,
        helpful=helpful,
        not_helpful=not_helpful,
        helpful_rate=helpful / rated if rated else None,
        by_category={str(category): int(count) for category, count in categories.all()},
    )


@router.post("/evaluations", response_model=AIEvaluationOut, status_code=status.HTTP_200_OK)
async def submit_evaluation(
    data: AIEvaluationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> AIEvaluationOut:
    execution = await db.scalar(
        select(AIExecution).where(
            AIExecution.organization_id == user.organization_id,
            AIExecution.id == data.execution_id,
            AIExecution.kind == "reply_draft",
            AIExecution.status == "succeeded",
        )
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="Completed reply draft not found")
    evaluation = await db.scalar(
        select(AIEvaluation)
        .where(
            AIEvaluation.organization_id == user.organization_id,
            AIEvaluation.execution_id == execution.id,
            AIEvaluation.evaluator_user_id == user.id,
        )
        .with_for_update()
    )
    if evaluation is None:
        evaluation = AIEvaluation(
            organization_id=user.organization_id,
            execution_id=execution.id,
            evaluator_user_id=user.id,
            rating=data.rating,
            category=data.category,
        )
        db.add(evaluation)
    else:
        evaluation.rating = data.rating
        evaluation.category = data.category
        evaluation.updated_at = datetime.now(UTC)
    await db.flush()
    return AIEvaluationOut.model_validate(evaluation)


@router.get("/background-failures", response_model=FailedBackgroundJobsOut)
async def failed_background_jobs(
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FailedBackgroundJobsOut:
    """List bounded tenant-owned terminal failures without private job payloads."""
    sources = [
        (AIExecution, AIExecution.status == "failed", AIExecution.completed_at, AIExecution.error_code, AIExecution.attempt_count, AIExecution.manual_retry_count, "ai_execution", None),
        (AutomationExecution, AutomationExecution.status == "failed", AutomationExecution.completed_at, AutomationExecution.error_code, AutomationExecution.attempt_count, None, "automation_execution", None),
        (CatalogSyncJob, CatalogSyncJob.status == "failed", CatalogSyncJob.completed_at, CatalogSyncJob.last_error_code, CatalogSyncJob.attempt_count, CatalogSyncJob.manual_retry_count, "catalog_sync", None),
        (CatalogWebhookEvent, CatalogWebhookEvent.status == "failed", CatalogWebhookEvent.completed_at, CatalogWebhookEvent.last_error_code, CatalogWebhookEvent.attempt_count, None, "catalog_webhook", None),
        (DocumentIngestionJob, DocumentIngestionJob.status == "failed", DocumentIngestionJob.completed_at, None, DocumentIngestionJob.attempt_count, None, "document_ingestion", DocumentIngestionJob.document_id),
        (CommerceAction, CommerceAction.execution_status == "failed", CommerceAction.execution_completed_at, CommerceAction.execution_error_code, CommerceAction.execution_attempt_count, None, "commerce_action", None),
        (IntegrationDeliveryJob, IntegrationDeliveryJob.status == "failed", IntegrationDeliveryJob.completed_at, IntegrationDeliveryJob.last_error_code, IntegrationDeliveryJob.attempt_count, None, "outbound_delivery", None),
    ]
    statements = []
    for model, failed_condition, failed_at, error_code, attempts, manual_retries, kind, resource_id in sources:
        statements.append(
            select(
                model.id.label("job_id"),
                literal(kind, type_=String(32)).label("job_kind"),
                func.coalesce(failed_at, model.updated_at).label("failed_at"),
                attempts.label("attempts"),
                (error_code if error_code is not None else literal(None, type_=String(80))).label("error_code"),
                (manual_retries if manual_retries is not None else literal(0)).label("manual_retry_count"),
                (resource_id if resource_id is not None else literal(None, type_=Uuid(as_uuid=True))).label("resource_id"),
                model.correlation_id.label("correlation_id"),
            ).where(model.organization_id == user.organization_id, failed_condition)
        )

    all_failures = union_all(*statements).subquery()
    total_failed = await db.scalar(select(func.count()).select_from(all_failures))
    result = await db.execute(
        select(all_failures)
        .order_by(all_failures.c.failed_at.desc(), all_failures.c.job_id.desc())
        .limit(limit)
    )
    items = []
    for row in result.mappings():
        raw_code = row["error_code"]
        safe_code = raw_code if isinstance(raw_code, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", raw_code) else None
        items.append(
            FailedBackgroundJobOut(
                job_id=row["job_id"],
                document_id=row["resource_id"] if row["job_kind"] == "document_ingestion" else None,
                correlation_id=(
                    row["correlation_id"]
                    if isinstance(row["correlation_id"], str)
                    and re.fullmatch(r"[A-Za-z0-9._:-]{8,64}", row["correlation_id"])
                    else None
                ),
                job_kind=row["job_kind"],
                failed_at=row["failed_at"],
                attempts=row["attempts"],
                error_code=safe_code,
                manual_retry_count=row["manual_retry_count"],
                manual_retry_available=(row["job_kind"] in {"ai_execution", "catalog_sync"} and row["manual_retry_count"] < 3),
            )
        )
    return FailedBackgroundJobsOut(
        generated_at=datetime.now(UTC),
        total_failed=int(total_failed or 0),
        items=items,
    )


@router.get("/job-trace", response_model=JobTraceOut)
async def job_trace(
    correlation_id: str = Query(min_length=8, max_length=64),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobTraceOut:
    """Show safe lifecycle summaries for jobs started by one workspace request."""
    if re.fullmatch(r"[A-Za-z0-9._:-]{8,64}", correlation_id) is None:
        raise HTTPException(status_code=422, detail="Invalid correlation ID")

    def trace_row(model, kind: str, error_column):
        return select(
            literal(kind, type_=String(32)).label("job_kind"),
            model.id.label("job_id"),
            model.status.label("status"),
            model.created_at.label("created_at"),
            model.completed_at.label("completed_at"),
            model.attempt_count.label("attempts"),
            model.max_attempts.label("max_attempts"),
            error_column.label("error_code"),
        ).where(
            model.organization_id == user.organization_id,
            model.correlation_id == correlation_id,
        )

    trace_rows = union_all(
        trace_row(AIExecution, "ai_execution", AIExecution.error_code),
        trace_row(AutomationExecution, "automation_execution", AutomationExecution.error_code),
        trace_row(DocumentIngestionJob, "document_ingestion", literal(None, type_=String(80))),
        select(
            literal("commerce_action", type_=String(32)).label("job_kind"),
            CommerceAction.id.label("job_id"),
            func.concat(CommerceAction.approval_status, "/", CommerceAction.execution_status).label("status"),
            CommerceAction.created_at.label("created_at"),
            CommerceAction.execution_completed_at.label("completed_at"),
            CommerceAction.execution_attempt_count.label("attempts"),
            literal(None, type_=Integer()).label("max_attempts"),
            CommerceAction.execution_error_code.label("error_code"),
        ).where(
            CommerceAction.organization_id == user.organization_id,
            CommerceAction.correlation_id == correlation_id,
        ),
        trace_row(CatalogSyncJob, "catalog_sync", CatalogSyncJob.last_error_code),
        trace_row(CatalogWebhookEvent, "catalog_webhook", CatalogWebhookEvent.last_error_code),
        trace_row(IntegrationDeliveryJob, "outbound_delivery", IntegrationDeliveryJob.last_error_code),
    ).subquery("job_trace")
    rows = await db.execute(
        select(trace_rows)
        .order_by(trace_rows.c.created_at, trace_rows.c.job_kind, trace_rows.c.job_id)
        .limit(100)
    )
    events = []
    for row in rows.mappings():
        raw_code = row["error_code"]
        safe_code = raw_code if isinstance(raw_code, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", raw_code) else None
        events.append(
            JobTraceEventOut(
                job_id=row["job_id"],
                job_kind=row["job_kind"],
                status=row["status"],
                created_at=row["created_at"],
                completed_at=row["completed_at"],
                attempts=row["attempts"],
                max_attempts=row["max_attempts"],
                error_code=safe_code,
            )
        )
    return JobTraceOut(
        correlation_id=correlation_id,
        generated_at=datetime.now(UTC),
        events=events,
    )


