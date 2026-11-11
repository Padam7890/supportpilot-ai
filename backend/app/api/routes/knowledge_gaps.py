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
from app.models.knowledge_document import KnowledgeDocument, KnowledgeDocumentSource, DocumentIngestionJob, DocumentChunk, DocumentEmbedding, DocumentEmbeddingJob
from app.models.knowledge_base import KnowledgeBase
from app.features.ai.domain.content_hash import PENDING_CONTENT_REVISION
from app.api.routes.knowledge import _resolve_knowledge_base
from app.services.knowledge_base_audit import record_knowledge_base_audit
from app.core.observability import current_correlation_id
from app.core.config import settings
from app.features.ai.domain.knowledge_gap_policy import faq_suggestion
from app.features.ai.application.knowledge_gap_reconciliation import reconcile_review

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
    offset: int = Query(default=0, ge=0, le=10000),
    threshold: float = Query(default=0.86, gt=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> GroupPage:
    from app.features.ai.application.knowledge_gap_grouping import list_semantic_groups
    from app.features.ai.infrastructure.embedding_gateway import EmbeddingProviderError
    try:
        groups = await list_semantic_groups(db, organization_id=user.organization_id, limit=limit, offset=offset, threshold=threshold)
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
    if len(ids) != len(payload.gap_ids):
        raise HTTPException(status_code=422, detail="Duplicate gap IDs are not allowed")
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


class FAQReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    gap_id: UUID
    document_id: UUID
    reviewer_id: UUID
    question: str
    answer: str
    status: str


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
        await reconcile_review(db, record)
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



class AtomicFAQPublish(BaseModel):
    gap_ids: list[UUID] = Field(min_length=1, max_length=100)
    knowledge_base_id: UUID
    question: str = Field(min_length=1, max_length=1000)
    answer: str = Field(min_length=1, max_length=10000)


class AtomicFAQResult(BaseModel):
    document_id: UUID
    status: str
    already_submitted: bool


@router.post("/groups/publish", response_model=AtomicFAQResult)
async def publish_reviewed_faq(
    payload: AtomicFAQPublish,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AtomicFAQResult:
    """Create the FAQ document, source, ingestion job and review links atomically.

    The tenant's gap rows are locked to serialize competing submissions. A retry
    with the same group returns the existing document; partial overlap is a conflict.
    """
    ids = sorted(set(payload.gap_ids))
    if len(ids) != len(payload.gap_ids):
        raise HTTPException(status_code=422, detail="Duplicate gap IDs are not allowed")
    question, answer = payload.question.strip(), payload.answer.strip()
    if not question or not answer:
        raise HTTPException(status_code=422, detail="Question and verified answer are required")
    gaps = (await db.scalars(
        select(KnowledgeGap).where(
            KnowledgeGap.organization_id == user.organization_id,
            KnowledgeGap.id.in_(ids),
        ).order_by(KnowledgeGap.id).with_for_update()
    )).all()
    if len(gaps) != len(ids):
        raise HTTPException(status_code=404, detail="One or more knowledge gaps not found")
    existing = (await db.scalars(select(KnowledgeGapReview).where(
        KnowledgeGapReview.organization_id == user.organization_id,
        KnowledgeGapReview.gap_id.in_(ids),
    ))).all()
    if existing:
        if (len(existing) == len(ids) and len({r.document_id for r in existing}) == 1
            and all(r.question == question and r.answer == answer for r in existing)):
            linked_document = await db.scalar(select(KnowledgeDocument).where(
                KnowledgeDocument.organization_id == user.organization_id,
                KnowledgeDocument.id == existing[0].document_id,
                KnowledgeDocument.knowledge_base_id == payload.knowledge_base_id,
                KnowledgeDocument.deleted_at.is_(None),
            ))
            if linked_document is not None:
                return AtomicFAQResult(document_id=linked_document.id, status="already_submitted", already_submitted=True)
        raise HTTPException(status_code=409, detail="Some questions already have a linked FAQ")
    selected_base = await _resolve_knowledge_base(
        db, user.organization_id, payload.knowledge_base_id, require_active=True
    )
    content = f"# {question}\n\n{answer}\n".encode("utf-8")
    document = KnowledgeDocument(
        organization_id=user.organization_id,
        name=f"FAQ-{ids[0]}.md",
        content_type="text/markdown",
        size_bytes=len(content),
        status="queued",
        uploaded_by_user_id=user.id,
        knowledge_base_id=selected_base.id,
        content_revision=PENDING_CONTENT_REVISION,
    )
    db.add(document)
    await db.flush()
    db.add(KnowledgeDocumentSource(
        organization_id=user.organization_id, document_id=document.id, content=content,
    ))
    db.add(DocumentIngestionJob(
        organization_id=user.organization_id, document_id=document.id,
        correlation_id=current_correlation_id(), status="queued",
    ))
    record_knowledge_base_audit(
        db, organization_id=user.organization_id,
        knowledge_base_id=selected_base.id, actor_user_id=user.id,
        event_type="document_uploaded",
        details={"document_id": str(document.id), "size_bytes": len(content), "content_type": "text/markdown"},
    )
    for gap in gaps:
        db.add(KnowledgeGapReview(
            organization_id=user.organization_id, gap_id=gap.id,
            document_id=document.id, reviewer_id=user.id,
            question=question, answer=answer, status="pending_ingestion",
        ))
    await db.flush()
    return AtomicFAQResult(document_id=document.id, status="queued", already_submitted=False)
