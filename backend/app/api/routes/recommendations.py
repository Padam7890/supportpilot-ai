"""Authenticated, versioned API for asynchronous product recommendations."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.models import AIExecution, Organization, User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.recommendations import RecommendationExecutionOut, RecommendationRequest

router = APIRouter(prefix="/recommendations", tags=["product recommendations"], responses=COMMON_ERROR_RESPONSES)
MAX_ACTIVE_RECOMMENDATIONS = 5


@router.post("", response_model=RecommendationExecutionOut, status_code=status.HTTP_202_ACCEPTED)
async def create_recommendation(
    data: RecommendationRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> RecommendationExecutionOut:
    await db.scalar(select(Organization.id).where(Organization.id == user.organization_id).with_for_update())
    active = await db.scalar(select(func.count(AIExecution.id)).where(
        AIExecution.organization_id == user.organization_id,
        AIExecution.kind == "recommendation",
        AIExecution.status.in_(["queued", "running"]),
    )) or 0
    if active >= MAX_ACTIVE_RECOMMENDATIONS:
        raise HTTPException(status_code=429, detail="Too many recommendation requests are already in progress")
    execution = AIExecution(
        organization_id=user.organization_id,
        requested_by_user_id=user.id,
        kind="recommendation",
        status="queued",
        question=data.question,
        max_attempts=settings.ai_provider_max_attempts,
    )
    db.add(execution)
    await db.flush()
    return RecommendationExecutionOut.model_validate(execution)


@router.get("/{execution_id}", response_model=RecommendationExecutionOut)
async def get_recommendation(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RecommendationExecutionOut:
    execution = await db.scalar(select(AIExecution).where(
        AIExecution.id == execution_id,
        AIExecution.organization_id == user.organization_id,
        AIExecution.kind == "recommendation",
    ))
    if execution is None:
        raise HTTPException(status_code=404, detail="Recommendation request not found")
    return RecommendationExecutionOut.model_validate(execution)
