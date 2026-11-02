from datetime import UTC, date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models import AIEvaluation, AIExecution, User
from app.schemas.analytics import (
    AIEvaluationCreate,
    AIEvaluationOut,
    AIEvaluationSummaryOut,
    AIUsageDay,
    AIUsageOut,
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


