"""Review-only knowledge gap API. Never publishes unapproved answers."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_roles
from app.db.session import get_db
from app.models import User
from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_gap_review import KnowledgeGapReview
from app.models.knowledge_document import KnowledgeDocument, DocumentChunk, DocumentEmbedding, DocumentEmbeddingJob
from app.core.config import settings
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


class GroupReview(BaseModel):
    gap_ids: list[UUID] = Field(min_length=1, max_length=100)
    status: str = Field(pattern="^(dismissed|resolved|open)$")


@router.post("/groups/review")
async def review_group(
    payload: GroupReview,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> dict[str, int]:
    ids = set(payload.gap_ids)
    rows = (await db.scalars(
        select(KnowledgeGap)
        .where(KnowledgeGap.organization_id == user.organization_id, KnowledgeGap.id.in_(ids))
        .with_for_update()
    )).all()
    if len(rows) != len(ids):
        raise HTTPException(status_code=404, detail="One or more knowledge gaps not found")
    for row in rows:
        row.status = payload.status
    await db.flush()
    return {"updated": len(rows)}


class FAQPublicationRecord(BaseModel):
    gap_ids: list[UUID] = Field(min_length=1, max_length=100)
    document_id: UUID
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=10000)


class FAQReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    gap_id: UUID
    document_id: UUID
    reviewer_id: UUID
    question: str
    answer: str
    status: str


@router.post("/groups/publications", response_model=list[FAQReviewOut])
async def record_faq_publication(
    payload: FAQPublicationRecord,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> list[FAQReviewOut]:
    ids = set(payload.gap_ids)
    document = await db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.organization_id == user.organization_id,
        KnowledgeDocument.id == payload.document_id,
        KnowledgeDocument.uploaded_by_user_id == user.id,
        KnowledgeDocument.deleted_at.is_(None),
    ))
    if document is None:
        raise HTTPException(status_code=404, detail="Uploaded FAQ document not found")
    gaps = (await db.scalars(select(KnowledgeGap).where(
        KnowledgeGap.organization_id == user.organization_id,
        KnowledgeGap.id.in_(ids),
    ).with_for_update())).all()
    if len(gaps) != len(ids):
        raise HTTPException(status_code=404, detail="One or more knowledge gaps not found")
    # A gap with an already linked FAQ cannot be silently uploaded again.
    previously_linked = (await db.scalars(select(KnowledgeGapReview).where(
        KnowledgeGapReview.organization_id == user.organization_id,
        KnowledgeGapReview.gap_id.in_(ids),
        KnowledgeGapReview.document_id != document.id,
    ))).all()
    if previously_linked:
        raise HTTPException(status_code=409, detail="A knowledge gap already has a linked FAQ document")
    existing = (await db.scalars(select(KnowledgeGapReview).where(
        KnowledgeGapReview.organization_id == user.organization_id,
        KnowledgeGapReview.document_id == document.id,
        KnowledgeGapReview.gap_id.in_(ids),
    ))).all()
    by_gap = {record.gap_id: record for record in existing}
    for gap in gaps:
        if gap.id not in by_gap:
            record = KnowledgeGapReview(
                organization_id=user.organization_id, gap_id=gap.id,
                document_id=document.id, reviewer_id=user.id,
                question=payload.question.strip(), answer=payload.answer.strip(),
                status="pending_ingestion",
            )
            db.add(record)
            by_gap[gap.id] = record
    await db.flush()
    return [FAQReviewOut.model_validate(by_gap[gap_id]) for gap_id in ids]


async def _reconcile_review_readiness(db: AsyncSession, record: KnowledgeGapReview) -> None:
    """Check actual ingestion and versioned embedding coverage before marking ready."""
    document = await db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.organization_id == record.organization_id,
        KnowledgeDocument.id == record.document_id,
        KnowledgeDocument.deleted_at.is_(None),
    ))
    if document is None or document.status == "failed":
        record.status = "failed"
        return
    if document.status != "ready":
        record.status = "pending_ingestion"
        return
    total_chunks = await db.scalar(select(func.count()).select_from(DocumentChunk).where(
        DocumentChunk.organization_id == record.organization_id,
        DocumentChunk.document_id == record.document_id,
    ))
    if not total_chunks:
        record.status = "pending_embeddings"
        return
    job = await db.scalar(select(DocumentEmbeddingJob).where(
        DocumentEmbeddingJob.organization_id == record.organization_id,
        DocumentEmbeddingJob.document_id == record.document_id,
        DocumentEmbeddingJob.embedding_model == settings.ai_embedding_model,
        DocumentEmbeddingJob.embedding_version == settings.ai_embedding_version,
    ))
    if job is None or job.status != "succeeded":
        record.status = "failed" if job is not None and job.status == "failed" else "pending_embeddings"
        return
    embedded_chunks = await db.scalar(select(func.count()).select_from(DocumentEmbedding).where(
        DocumentEmbedding.organization_id == record.organization_id,
        DocumentEmbedding.document_id == record.document_id,
        DocumentEmbedding.embedding_model == settings.ai_embedding_model,
        DocumentEmbedding.embedding_version == settings.ai_embedding_version,
    ))
    record.status = "ready" if embedded_chunks == total_chunks else "pending_embeddings"


@router.get("/reviews", response_model=list[FAQReviewOut])
async def list_faq_reviews(
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> list[FAQReviewOut]:
    records = (await db.scalars(select(KnowledgeGapReview).where(
        KnowledgeGapReview.organization_id == user.organization_id,
    ).order_by(KnowledgeGapReview.created_at.desc()).limit(limit))).all()
    for record in records:
        await _reconcile_review_readiness(db, record)
    await db.flush()
    return [FAQReviewOut.model_validate(record) for record in records]

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


