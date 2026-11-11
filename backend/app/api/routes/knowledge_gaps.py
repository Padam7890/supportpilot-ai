"""Review-only knowledge gap API. Never publishes unapproved answers."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.api.routes.knowledge import _resolve_knowledge_base
from app.core.config import settings
from app.core.observability import current_correlation_id
from app.db.session import get_db
from app.features.ai.application.knowledge_gap_dashboard import (
    KnowledgeGapDashboard,
    QuestionView,
    load_knowledge_gap_dashboard,
)
from app.features.ai.application.knowledge_gap_reconciliation import reconcile_review
from app.features.ai.domain.content_hash import PENDING_CONTENT_REVISION
from app.features.ai.domain.knowledge_gap_policy import faq_suggestion
from app.models import User
from app.models.knowledge_document import (
    DocumentIngestionJob,
    KnowledgeDocument,
    KnowledgeDocumentSource,
)
from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_gap_group import KnowledgeGapGroup, KnowledgeGapGroupMember
from app.models.knowledge_gap_review import KnowledgeGapReview
from app.services.knowledge_base_audit import record_knowledge_base_audit

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


@router.get("/dashboard", response_model=KnowledgeGapDashboard)
async def customer_question_dashboard(
    period: Literal["7", "30", "90", "all"] = "30",
    view: QuestionView = "all",
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeGapDashboard:
    return await load_knowledge_gap_dashboard(
        db, user.organization_id, days=None if period == "all" else int(period),
        view=view, search=search.strip(), limit=limit, offset=offset,
    )


class GroupOut(BaseModel):
    representative: str
    count: int
    gap_ids: list[UUID]


class GroupPage(BaseModel):
    items: list[GroupOut]
    has_more: bool


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
    total_open = await db.scalar(select(func.count()).select_from(KnowledgeGap).where(
        KnowledgeGap.organization_id == user.organization_id,
        KnowledgeGap.status == "open",
    ))
    return GroupPage(
        items=[GroupOut(representative=g.representative, count=g.count, gap_ids=list(g.gap_ids)) for g in groups],
        has_more=offset + limit < (total_open or 0),
    )


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
    if payload.status == "resolved":
        pending = (await db.scalars(select(KnowledgeGapReview).where(
            KnowledgeGapReview.organization_id == user.organization_id,
            KnowledgeGapReview.gap_id.in_(ids),
            KnowledgeGapReview.status != "ready",
        ))).all()
        if pending:
            raise HTTPException(status_code=409, detail="FAQ ingestion must be ready before resolving linked gaps")
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
    if payload.status == "resolved":
        pending = await db.scalar(select(KnowledgeGapReview).where(
            KnowledgeGapReview.organization_id == user.organization_id,
            KnowledgeGapReview.gap_id == gap_id,
            KnowledgeGapReview.status != "ready",
        ))
        if pending is not None:
            raise HTTPException(status_code=409, detail="FAQ ingestion must be ready before resolving linked gaps")
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
    # Security: only currently open, tenant-owned questions can be used to
    # create a new FAQ. Prevent publishing stale, dismissed or resolved gaps.
    if any(gap.status != "open" for gap in gaps):
        raise HTTPException(status_code=409, detail="Only open knowledge gaps can be published")
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
    content = f"# {question}\n\n{answer}\n".encode()
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


class DurableGroupCreate(BaseModel):
    gap_ids: list[UUID] = Field(min_length=1, max_length=100)


class DurableGroupOut(BaseModel):
    id: UUID
    representative: str
    gap_ids: list[UUID]


@router.post("/durable-groups", response_model=DurableGroupOut)
async def create_durable_group(
    payload: DurableGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> DurableGroupOut:
    ids = set(payload.gap_ids)
    if len(ids) != len(payload.gap_ids):
        raise HTTPException(status_code=422, detail="Duplicate gap IDs")
    gaps = (await db.scalars(select(KnowledgeGap).where(
        KnowledgeGap.organization_id == user.organization_id,
        KnowledgeGap.id.in_(ids), KnowledgeGap.status == "open",
    ).order_by(KnowledgeGap.id).with_for_update())).all()
    if len(gaps) != len(ids):
        raise HTTPException(status_code=404, detail="Open knowledge gaps not found")
    occupied = await db.scalar(select(KnowledgeGapGroupMember).where(
        KnowledgeGapGroupMember.organization_id == user.organization_id,
        KnowledgeGapGroupMember.gap_id.in_(ids),
    ))
    if occupied:
        raise HTTPException(status_code=409, detail="A gap already belongs to a durable group")
    group = KnowledgeGapGroup(organization_id=user.organization_id, representative=gaps[0].question)
    db.add(group)
    await db.flush()
    for gap in gaps:
        db.add(KnowledgeGapGroupMember(organization_id=user.organization_id, group_id=group.id, gap_id=gap.id))
    await db.flush()
    return DurableGroupOut(id=group.id, representative=group.representative, gap_ids=[gap.id for gap in gaps])


@router.get("/durable-groups", response_model=list[DurableGroupOut])
async def list_durable_groups(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> list[DurableGroupOut]:
    groups = (await db.scalars(select(KnowledgeGapGroup).where(
        KnowledgeGapGroup.organization_id == user.organization_id,
    ).order_by(KnowledgeGapGroup.created_at.desc(), KnowledgeGapGroup.id.desc()).offset(offset).limit(limit))).all()
    if not groups:
        return []
    members = (await db.scalars(select(KnowledgeGapGroupMember).where(
        KnowledgeGapGroupMember.organization_id == user.organization_id,
        KnowledgeGapGroupMember.group_id.in_([group.id for group in groups]),
    ))).all()
    by_group: dict[UUID, list[UUID]] = {group.id: [] for group in groups}
    for member in members:
        by_group[member.group_id].append(member.gap_id)
    return [DurableGroupOut(id=group.id, representative=group.representative, gap_ids=by_group[group.id]) for group in groups]


class DurableGroupMove(BaseModel):
    gap_ids: list[UUID] = Field(min_length=1, max_length=100)


@router.post("/durable-groups/{group_id}/members")
async def move_durable_group_members(
    group_id: UUID,
    payload: DurableGroupMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> dict[str, int]:
    ids = set(payload.gap_ids)
    if len(ids) != len(payload.gap_ids):
        raise HTTPException(status_code=422, detail="Duplicate gap IDs")
    target = await db.scalar(select(KnowledgeGapGroup).where(
        KnowledgeGapGroup.organization_id == user.organization_id,
        KnowledgeGapGroup.id == group_id,
    ).with_for_update())
    if target is None:
        raise HTTPException(status_code=404, detail="Target group not found")
    gaps = (await db.scalars(select(KnowledgeGap).where(
        KnowledgeGap.organization_id == user.organization_id,
        KnowledgeGap.id.in_(ids), KnowledgeGap.status == "open",
    ).order_by(KnowledgeGap.id).with_for_update())).all()
    if len(gaps) != len(ids):
        raise HTTPException(status_code=404, detail="Open gaps not found")
    # Lock existing memberships in deterministic order before reassignment.
    memberships = (await db.scalars(select(KnowledgeGapGroupMember).where(
        KnowledgeGapGroupMember.organization_id == user.organization_id,
        KnowledgeGapGroupMember.gap_id.in_(ids),
    ).order_by(KnowledgeGapGroupMember.gap_id).with_for_update())).all()
    assigned = {membership.gap_id for membership in memberships}
    for membership in memberships:
        membership.group_id = group_id
    for gap in gaps:
        if gap.id not in assigned:
            db.add(KnowledgeGapGroupMember(
                organization_id=user.organization_id, group_id=group_id, gap_id=gap.id,
            ))
    await db.flush()
    return {"moved": len(ids)}


@router.delete("/durable-groups/{group_id}", status_code=204)
async def delete_durable_group(
    group_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> None:
    """Delete a review grouping without deleting the underlying gaps."""
    from sqlalchemy import delete
    group = await db.scalar(select(KnowledgeGapGroup).where(
        KnowledgeGapGroup.organization_id == user.organization_id,
        KnowledgeGapGroup.id == group_id,
    ).with_for_update())
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    await db.execute(delete(KnowledgeGapGroupMember).where(
        KnowledgeGapGroupMember.organization_id == user.organization_id,
        KnowledgeGapGroupMember.group_id == group_id,
    ))
    await db.delete(group)
    await db.flush()


class SemanticGroupAssignment(BaseModel):
    limit: int = Field(default=100, ge=1, le=100)
    threshold: float = Field(default=0.86, gt=0.0, le=1.0)


@router.post("/durable-groups/auto-assign")
async def auto_assign_semantic_groups(
    payload: SemanticGroupAssignment,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> dict[str, int]:
    """Persist semantic candidates across review pages; never override manual memberships."""
    from app.features.ai.application.knowledge_gap_grouping import (
        cosine_similarity,
    )
    from app.features.ai.infrastructure.embedding_gateway import EmbeddingProviderError, embed_texts
    from app.models.knowledge_gap_embedding import KnowledgeGapEmbedding
    # Serialize assignments per tenant without blocking other tenants.
    await db.execute(select(KnowledgeGap).where(
        KnowledgeGap.organization_id == user.organization_id,
        KnowledgeGap.status == "open",
    ).order_by(KnowledgeGap.id).limit(payload.limit).with_for_update())
    existing = (await db.scalars(select(KnowledgeGapGroup).where(
        KnowledgeGapGroup.organization_id == user.organization_id,
    ).order_by(KnowledgeGapGroup.id).with_for_update())).all()
    assigned = set((await db.scalars(select(KnowledgeGapGroupMember.gap_id).where(
        KnowledgeGapGroupMember.organization_id == user.organization_id,
    ))).all())
    # Scan a bounded source window; exclude already assigned gaps before embedding.
    gaps = (await db.scalars(select(KnowledgeGap).where(
        KnowledgeGap.organization_id == user.organization_id,
        KnowledgeGap.status == "open",
        KnowledgeGap.id.not_in(assigned) if assigned else True,
    ).order_by(KnowledgeGap.created_at, KnowledgeGap.id).limit(payload.limit).with_for_update())).all()
    if not gaps:
        return {"assigned": 0, "created": 0}
    model, version = settings.ai_embedding_model, settings.ai_embedding_version
    if not model:
        raise HTTPException(status_code=503, detail="Embedding model is not configured")
    from hashlib import sha256
    cached = (await db.scalars(select(KnowledgeGapEmbedding).where(
        KnowledgeGapEmbedding.organization_id == user.organization_id,
        KnowledgeGapEmbedding.gap_id.in_([gap.id for gap in gaps]),
        KnowledgeGapEmbedding.model == model,
        KnowledgeGapEmbedding.version == version,
    ))).all()
    cache = {item.gap_id: item for item in cached}
    vectors = {}
    missing = []
    for gap in gaps:
        item = cache.get(gap.id)
        if item is not None and item.question_hash == sha256(gap.question.encode()).hexdigest() and len(item.values) == item.dimensions:
            vectors[gap.id] = item.values
        else:
            missing.append(gap)
    try:
        for start in range(0, len(missing), max(1, settings.ai_embedding_batch_size)):
            batch = missing[start:start + max(1, settings.ai_embedding_batch_size)]
            results = await embed_texts([gap.question for gap in batch], model=model)
            if len(results) != len(batch):
                raise ValueError("Embedding provider returned wrong vector count")
            from sqlalchemy.dialects.postgresql import insert
            for gap, result in zip(batch, results, strict=True):
                vectors[gap.id] = result.values
                stmt = insert(KnowledgeGapEmbedding).values(
                    organization_id=user.organization_id, gap_id=gap.id, model=model,
                    version=version, question_hash=sha256(gap.question.encode()).hexdigest(),
                    dimensions=len(result.values), values=result.values,
                ).on_conflict_do_update(
                    index_elements=["organization_id", "gap_id", "model", "version"],
                    set_={"question_hash": sha256(gap.question.encode()).hexdigest(),
                          "dimensions": len(result.values), "values": result.values},
                )
                await db.execute(stmt)
        representative_vectors = {}
        for group in existing:
            result = await embed_texts([group.representative], model=model)
            representative_vectors[group.id] = result[0].values
    except EmbeddingProviderError as exc:
        raise HTTPException(status_code=503, detail="Semantic grouping unavailable") from exc
    created = 0
    for gap in gaps:
        vector = vectors[gap.id]
        matches = [(cosine_similarity(vector, representative_vectors[group.id]), group)
                   for group in existing if len(vector) == len(representative_vectors[group.id])]
        score, target = max(matches, key=lambda item: item[0]) if matches else (0.0, None)
        if target is None or score < payload.threshold:
            target = KnowledgeGapGroup(organization_id=user.organization_id, representative=gap.question)
            db.add(target)
            await db.flush()
            existing.append(target)
            representative_vectors[target.id] = vector
            created += 1
        db.add(KnowledgeGapGroupMember(
            organization_id=user.organization_id, group_id=target.id, gap_id=gap.id,
        ))
    await db.flush()
    return {"assigned": len(gaps), "created": created}
