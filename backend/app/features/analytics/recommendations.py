"""Recommendation analytics endpoints for the analytics feature."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.features.analytics.router import date_predicate, date_window
from app.models import AIAgent, AIExecution, CatalogProduct, Message, RecommendationEvent, User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.recommendation_settings import (
    RecommendationAnalyticsOut,
    RecommendationBotFunnel,
    RecommendationTrendPoint,
)

recommendations_router = APIRouter(prefix="/analytics", tags=["analytics"], responses=COMMON_ERROR_RESPONSES)

@recommendations_router.get("/recommendations", response_model=RecommendationAnalyticsOut)
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
    bot_rows = await db.execute(
        select(
            AIAgent.id,
            AIAgent.name,
            func.count(RecommendationEvent.id).filter(RecommendationEvent.event_type == "impression"),
            func.count(RecommendationEvent.id).filter(RecommendationEvent.event_type == "product_click"),
            func.count(RecommendationEvent.id).filter(RecommendationEvent.event_type == "comparison"),
            func.count(RecommendationEvent.id).filter(RecommendationEvent.event_type == "rejection"),
            func.count(RecommendationEvent.id).filter(RecommendationEvent.event_type == "no_result"),
            func.count(RecommendationEvent.id).filter(RecommendationEvent.event_type == "human_handoff"),
        )
        .join(
            Message,
            and_(
                Message.organization_id == RecommendationEvent.organization_id,
                Message.id == RecommendationEvent.message_id,
            ),
        )
        .join(
            AIExecution,
            and_(
                AIExecution.organization_id == Message.organization_id,
                or_(
                    AIExecution.id == Message.source_ai_execution_id,
                    AIExecution.source_message_id == Message.id,
                ),
                AIExecution.kind == "widget_reply",
            ),
        )
        .join(
            AIAgent,
            and_(
                AIAgent.organization_id == AIExecution.organization_id,
                AIAgent.id == AIExecution.ai_agent_id,
            ),
        )
        .where(*event_scope, AIAgent.organization_id == user.organization_id)
        .group_by(AIAgent.id, AIAgent.name)
        .order_by(func.count(RecommendationEvent.id).desc(), AIAgent.name.asc())
        .limit(50)
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
        bots=[
            RecommendationBotFunnel(
                bot_id=bot_id,
                bot_name=bot_name,
                impressions=int(impressions),
                product_clicks=int(clicks),
                comparisons=int(comparisons),
                rejections=int(rejections),
                no_results=int(no_results),
                human_handoffs=int(handoffs),
            )
            for bot_id, bot_name, impressions, clicks, comparisons, rejections, no_results, handoffs
            in bot_rows.all()
        ],
    )

