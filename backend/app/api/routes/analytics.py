from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models import AIEvaluation, AIExecution, CatalogProduct, RecommendationEvent, User
from app.schemas.analytics import (
    AIEvaluationCreate,
    AIEvaluationOut,
    AIEvaluationSummaryOut,
    AIUsageDay,
    AIUsageOut,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.recommendation_settings import RecommendationAnalyticsOut, RecommendationTrendPoint

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
    daily_rows = await db.execute(
        select(
            func.date(AIExecution.created_at),
            func.count(AIExecution.id),
            prompt_tokens,
            completion_tokens,
        )
        .where(*predicate)
        .group_by(func.date(AIExecution.created_at))
        .order_by(func.date(AIExecution.created_at))
    )
    daily_map = {
        day: (int(executions), int(day_prompt), int(day_completion))
        for day, executions, day_prompt, day_completion in daily_rows.all()
    }
    daily = [
        AIUsageDay(
            date=day,
            executions=daily_map.get(day, (0, 0, 0))[0],
            prompt_tokens=daily_map.get(day, (0, 0, 0))[1],
            completion_tokens=daily_map.get(day, (0, 0, 0))[2],
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


@router.get("/recommendations", response_model=RecommendationAnalyticsOut)
async def recommendation_analytics(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecommendationAnalyticsOut:
    """Tenant scoped funnel and operational measurements; commerce conversion is unavailable until trusted events exist."""
    start, end = date_window(start_date, end_date)
    event_scope = (
        RecommendationEvent.organization_id == user.organization_id,
        date_predicate(RecommendationEvent.created_at, start, end),
    )
    counts = await db.execute(
        select(RecommendationEvent.event_type, func.count(RecommendationEvent.id))
        .where(*event_scope).group_by(RecommendationEvent.event_type)
    )
    event_counts = {key: int(value) for key, value in counts.all()}

    trend_rows = await db.execute(
        select(func.date(RecommendationEvent.created_at), RecommendationEvent.event_type, func.count(RecommendationEvent.id))
        .where(*event_scope).group_by(func.date(RecommendationEvent.created_at), RecommendationEvent.event_type)
    )
    per_day: dict[date, dict[str, int]] = {}
    for day, event_type, count in trend_rows.all():
        per_day.setdefault(day, {})[event_type] = int(count)
    trends = [RecommendationTrendPoint(
        date=day.isoformat(),
        impressions=per_day.get(day, {}).get("impression", 0),
        clicks=per_day.get(day, {}).get("product_click", 0),
        comparisons=per_day.get(day, {}).get("comparison", 0),
        no_results=per_day.get(day, {}).get("no_result", 0),
        handoffs=per_day.get(day, {}).get("human_handoff", 0),
    ) for day in (start + timedelta(days=i) for i in range((end - start).days + 1))]

    async def product_leaders(event_type: str) -> list[dict[str, str | int]]:
        rows = await db.execute(
            select(CatalogProduct.id, CatalogProduct.title, func.count(RecommendationEvent.id).label("events"))
            .join(RecommendationEvent, RecommendationEvent.product_id == CatalogProduct.id)
            .where(*event_scope, RecommendationEvent.event_type == event_type, CatalogProduct.organization_id == user.organization_id)
            .group_by(CatalogProduct.id, CatalogProduct.title)
            .order_by(func.count(RecommendationEvent.id).desc(), CatalogProduct.title.asc())
            .limit(10)
        )
        return [{"product_id": str(pid), "title": title, "count": int(count)} for pid, title, count in rows.all()]

    category_rows = await db.execute(
        select(RecommendationEvent.query_category, func.count(RecommendationEvent.id))
        .where(*event_scope, RecommendationEvent.event_type == "no_result", RecommendationEvent.query_category.is_not(None))
        .group_by(RecommendationEvent.query_category).order_by(func.count(RecommendationEvent.id).desc()).limit(10)
    )
    execution_scope = (
        AIExecution.organization_id == user.organization_id,
        or_(
            AIExecution.kind == "recommendation",
            (AIExecution.kind == "widget_reply")
            & cast(AIExecution.tool_outcomes, String).ilike("%recommend_products%"),
            (AIExecution.kind == "widget_reply")
            & cast(AIExecution.tool_outcomes, String).ilike("%compare_products%"),
        ),
        date_predicate(AIExecution.created_at, start, end),
    )
    input_tokens = func.coalesce(func.sum(AIExecution.usage["prompt_tokens"].as_integer()), 0)
    output_tokens = func.coalesce(func.sum(AIExecution.usage["completion_tokens"].as_integer()), 0)
    exec_summary = await db.execute(select(
        input_tokens,
        output_tokens,
        func.count(AIExecution.id).filter(AIExecution.status == "failed"),
        func.avg(func.extract("epoch", AIExecution.completed_at - AIExecution.started_at)).filter(AIExecution.started_at.is_not(None), AIExecution.completed_at.is_not(None)),
    ).where(*execution_scope))
    prompt, completion, failures, latency_seconds = exec_summary.one()
    error_rows = await db.execute(
        select(AIExecution.error_code, func.count(AIExecution.id))
        .where(*execution_scope, AIExecution.status == "failed", AIExecution.error_code.is_not(None))
        .group_by(AIExecution.error_code)
        .order_by(func.count(AIExecution.id).desc())
        .limit(10)
    )
    cost = None
    if settings.ai_input_cost_per_million is not None and settings.ai_output_cost_per_million is not None:
        cost = (int(prompt) * settings.ai_input_cost_per_million + int(completion) * settings.ai_output_cost_per_million) / 1_000_000
    return RecommendationAnalyticsOut(
        start_date=start.isoformat(), end_date=end.isoformat(),
        impressions=event_counts.get("impression", 0), product_clicks=event_counts.get("product_click", 0),
        comparisons=event_counts.get("comparison", 0), add_to_cart=None,
        attributed_purchases=None, direct_purchases=None, assisted_purchases=None,
        rejected_recommendations=event_counts.get("rejection", 0), no_result_searches=event_counts.get("no_result", 0),
        human_handoffs=event_counts.get("human_handoff", 0),
        average_latency_ms=round(float(latency_seconds) * 1000) if latency_seconds is not None else None,
        prompt_tokens=int(prompt), completion_tokens=int(completion), estimated_cost_usd=cost,
        failed_executions=int(failures), conversion_tracking_available=False,
        error_codes=[{"code": str(code), "count": int(count)} for code, count in error_rows.all()],
        trends=trends, top_recommended_products=await product_leaders("impression"),
        top_clicked_products=await product_leaders("product_click"),
        no_result_categories=[{"category": str(category), "count": int(count)} for category, count in category_rows.all()],
    )
