"""Review-only knowledge gap API. Never publishes unapproved answers."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_roles
from app.db.session import get_db
from app.models import User
from app.models.knowledge_gap import KnowledgeGap
from app.features.ai.domain.knowledge_gap_policy import faq_suggestion

router = APIRouter(prefix="/knowledge/gaps", tags=["knowledge"])


class GapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    question: str
    reason: str
    status: str


class GapPage(BaseModel):
    items: list[GapOut]


class FAQSuggestion(BaseModel):
    question: str
    suggested_answer: str | None
    status: str


@router.get("", response_model=GapPage)
async def list_gaps(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> GapPage:
    rows = (await db.scalars(
        select(KnowledgeGap).where(KnowledgeGap.organization_id == user.organization_id)
        .order_by(KnowledgeGap.created_at.desc()).limit(limit)
    )).all()
    return GapPage(items=[GapOut.model_validate(row) for row in rows])


@router.get("/{gap_id}/faq-suggestion", response_model=FAQSuggestion)
async def suggest_faq(
    gap_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> FAQSuggestion:
    row = await db.scalar(select(KnowledgeGap).where(
        KnowledgeGap.organization_id == user.organization_id, KnowledgeGap.id == gap_id
    ))
    if row is None:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    return FAQSuggestion(**faq_suggestion(row.question))


class GroupOut(BaseModel):
    representative: str
    count: int
    gap_ids: list[UUID]


class GroupPage(BaseModel):
    items: list[GroupOut]


@router.get("/groups", response_model=GroupPage)
async def list_grouped_gaps(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> GroupPage:
    from app.features.ai.application.knowledge_gap_grouping import list_semantic_groups
    from app.features.ai.infrastructure.embedding_gateway import EmbeddingProviderError
    try:
        groups = await list_semantic_groups(db, organization_id=user.organization_id, limit=limit)
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=503, detail="Semantic grouping is temporarily unavailable") from exc
    return GroupPage(items=[GroupOut(representative=g.representative, count=g.count, gap_ids=list(g.gap_ids)) for g in groups])


class GapReview(BaseModel):
    status: str = Field(pattern="^(dismissed|resolved|open)$")


@router.patch("/{gap_id}", response_model=GapOut)
async def review_gap(
    gap_id: UUID,
    payload: GapReview,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> GapOut:
    row = await db.scalar(
        select(KnowledgeGap)
        .where(KnowledgeGap.organization_id == user.organization_id, KnowledgeGap.id == gap_id)
        .with_for_update()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    row.status = payload.status
    await db.flush()
    return GapOut.model_validate(row)
