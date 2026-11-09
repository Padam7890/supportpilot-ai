import re
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import PurePath
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, literal_column, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.observability import current_correlation_id
from app.core.config import settings
from app.db.session import get_db
from app.services.knowledge_base_audit import record_knowledge_base_audit
from app.features.ai.application.embedding_jobs import enqueue_document_embeddings
from app.features.ai.infrastructure.embedding_gateway import is_embedding_provider_configured
from app.models import (
    DocumentChunk,
    DocumentIngestionJob,
    DocumentEmbeddingJob,
    KnowledgeBase,
    KnowledgeDocument,
    KnowledgeDocumentSource,
    User,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.knowledge import (
    IngestionJobOut,
    KnowledgeDocumentMove,
    KnowledgeDocumentOut,
    KnowledgeDocumentPage,
    KnowledgeSourcePreviewOut,
    KnowledgeSearchPage,
    KnowledgeSearchResult,
    DocumentEmbeddingJobOut,
    DocumentEmbeddingBackfillOut,
)

from app.workers.domain.ingestion_errors import requires_replacement

router = APIRouter(prefix="/knowledge/documents", tags=["knowledge"], responses=COMMON_ERROR_RESPONSES)
INGESTION_HISTORY_LIMIT = 20
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
SOURCE_PREVIEW_MAX_BYTES = 32 * 1024
ALLOWED_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}


@router.post("/embeddings/backfill", response_model=DocumentEmbeddingBackfillOut, status_code=status.HTTP_202_ACCEPTED)
async def backfill_document_embeddings(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> DocumentEmbeddingBackfillOut:
    """Queue a bounded backfill for ready tenant documents using configured model version."""
    if not is_embedding_provider_configured() or not settings.ai_embedding_model:
        raise HTTPException(status_code=503, detail="Embedding provider is not configured")
    existing = DocumentEmbeddingJob
    documents = list(await db.scalars(
        select(KnowledgeDocument)
        .outerjoin(existing, (existing.organization_id == KnowledgeDocument.organization_id)
                   & (existing.document_id == KnowledgeDocument.id)
                   & (existing.embedding_model == settings.ai_embedding_model)
                   & (existing.embedding_version == settings.ai_embedding_version))
        .where(KnowledgeDocument.organization_id == user.organization_id,
               KnowledgeDocument.status == "ready", KnowledgeDocument.deleted_at.is_(None),
               (existing.id.is_(None)) | existing.status.in_(("failed", "cancelled")))
        .order_by(KnowledgeDocument.created_at, KnowledgeDocument.id)
        .limit(limit)
    ))
    job_ids = []
    for document in documents:
        job_id = await enqueue_document_embeddings(
            db, organization_id=user.organization_id, document_id=document.id,
            correlation_id=current_correlation_id(),
        )
        if job_id:
            job_ids.append(job_id)
    await db.commit()
    return DocumentEmbeddingBackfillOut(
        queued_count=len(job_ids), job_ids=job_ids,
        embedding_model=settings.ai_embedding_model,
        embedding_version=settings.ai_embedding_version,
    )


@router.post("/{document_id}/embeddings/reprocess", response_model=DocumentEmbeddingJobOut,
            status_code=status.HTTP_202_ACCEPTED)
async def reprocess_document_embeddings(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> DocumentEmbeddingJobOut:
    """Requeue embeddings for one ready document without reingesting its source."""
    if not is_embedding_provider_configured() or not settings.ai_embedding_model:
        raise HTTPException(status_code=503, detail="Embedding provider is not configured")
    document = await db.scalar(select(KnowledgeDocument).where(
        KnowledgeDocument.organization_id == user.organization_id,
        KnowledgeDocument.id == document_id,
        KnowledgeDocument.status == "ready",
        KnowledgeDocument.deleted_at.is_(None),
    ))
    if document is None:
        raise HTTPException(status_code=404, detail="Ready knowledge document not found")
    job_id = await enqueue_document_embeddings(
        db, organization_id=user.organization_id, document_id=document_id,
        correlation_id=current_correlation_id(),
    )
    if job_id is None:
        raise HTTPException(status_code=503, detail="Embedding job could not be queued")
    await db.commit()
    job = await db.scalar(select(DocumentEmbeddingJob).where(
        DocumentEmbeddingJob.organization_id == user.organization_id,
        DocumentEmbeddingJob.id == job_id,
    ))
    if job is None:
        raise HTTPException(status_code=500, detail="Embedding job was not persisted")
    return DocumentEmbeddingJobOut.model_validate(job)


async def document_out(db: AsyncSession, document: KnowledgeDocument) -> KnowledgeDocumentOut:
    jobs = await db.scalars(
        select(DocumentIngestionJob)
        .where(
            DocumentIngestionJob.organization_id == document.organization_id,
            DocumentIngestionJob.document_id == document.id,
        )
        .order_by(DocumentIngestionJob.created_at.desc(), DocumentIngestionJob.id.desc())
        .limit(INGESTION_HISTORY_LIMIT)
    )
    return serialize_document(document, jobs)


def serialize_document(
    document: KnowledgeDocument, jobs: Iterable[DocumentIngestionJob]
) -> KnowledgeDocumentOut:
    return KnowledgeDocumentOut(
        id=document.id,
        knowledge_base_id=document.knowledge_base_id,
        name=document.name,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.status,
        created_at=document.created_at,
        updated_at=document.updated_at,
        deleted_at=document.deleted_at,
        jobs=[
            IngestionJobOut.model_validate(job).model_copy(
                update={"requires_replacement": requires_replacement(job.last_error)}
            )
            for job in jobs
        ],
    )


@router.post(
    "",
    response_model=KnowledgeDocumentOut,
    status_code=status.HTTP_202_ACCEPTED,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                media_type: {"schema": {"type": "string", "format": "binary"}}
                for media_type in ("application/pdf", "text/plain", "text/markdown")
            },
        }
    },
)
async def upload_document(
    request: Request,
    name: str = Query(min_length=1, max_length=255),
    knowledge_base_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeDocumentOut:
    safe_name = PurePath(name.replace("\\", "/")).name.strip()
    suffix = PurePath(safe_name).suffix.lower()
    expected_type = ALLOWED_TYPES.get(suffix)
    supplied_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not expected_type or supplied_type != expected_type:
        raise HTTPException(status_code=415, detail="Upload a PDF, plain text, or Markdown document")
    content = bytearray()
    async for part in request.stream():
        if len(content) + len(part) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Document exceeds the 20 MB upload limit")
        content.extend(part)
    if not content:
        raise HTTPException(status_code=400, detail="Document is empty")

    selected_base = await _resolve_knowledge_base(
        db, user.organization_id, knowledge_base_id, require_active=True
    )
    document = KnowledgeDocument(
        organization_id=user.organization_id,
        name=safe_name,
        content_type=expected_type,
        size_bytes=len(content),
        status="queued",
        uploaded_by_user_id=user.id,
        knowledge_base_id=selected_base.id,
    )
    db.add(document)
    await db.flush()
    record_knowledge_base_audit(
        db,
        organization_id=user.organization_id,
        knowledge_base_id=selected_base.id,
        actor_user_id=user.id,
        event_type="document_uploaded",
        details={
            "document_id": str(document.id),
            "size_bytes": document.size_bytes,
            "content_type": document.content_type,
        },
    )
    db.add_all(
        [
            KnowledgeDocumentSource(
                organization_id=user.organization_id,
                document_id=document.id,
                content=bytes(content),
            ),
            DocumentIngestionJob(
                organization_id=user.organization_id,
                document_id=document.id,
                correlation_id=current_correlation_id(),
                status="queued",
            ),
        ]
    )
    await db.flush()
    return await document_out(db, document)


async def page_ingestion_history(
    db: AsyncSession, organization_id: UUID, document_ids: list[UUID]
) -> dict[UUID, list[DocumentIngestionJob]]:
    if not document_ids:
        return {}
    ranked = (
        select(
            DocumentIngestionJob.id,
            func.row_number().over(
                partition_by=DocumentIngestionJob.document_id,
                order_by=(DocumentIngestionJob.created_at.desc(), DocumentIngestionJob.id.desc()),
            ).label("position"),
        )
        .where(
            DocumentIngestionJob.organization_id == organization_id,
            DocumentIngestionJob.document_id.in_(document_ids),
        )
        .subquery()
    )
    jobs = await db.scalars(
        select(DocumentIngestionJob)
        .join(ranked, DocumentIngestionJob.id == ranked.c.id)
        .where(
            DocumentIngestionJob.organization_id == organization_id,
            ranked.c.position <= INGESTION_HISTORY_LIMIT,
        )
        .order_by(ranked.c.position)
    )
    history: dict[UUID, list[DocumentIngestionJob]] = defaultdict(list)
    for job in jobs:
        history[job.document_id].append(job)
    return history


@router.get("", response_model=KnowledgeDocumentPage)
async def list_documents(
    knowledge_base_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeDocumentPage:
    predicate = [
        KnowledgeDocument.organization_id == user.organization_id,
        KnowledgeDocument.deleted_at.is_(None),
    ]
    if knowledge_base_id:
        await _resolve_knowledge_base(db, user.organization_id, knowledge_base_id)
        predicate.append(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
    total = await db.scalar(
        select(func.count()).select_from(KnowledgeDocument).where(*predicate)
    ) or 0
    documents = await db.scalars(
        select(KnowledgeDocument)
        .where(*predicate)
        .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
        .limit(limit)
        .offset(offset)
    )
    page = documents.all()
    history = await page_ingestion_history(db, user.organization_id, [document.id for document in page])
    return KnowledgeDocumentPage(
        items=[serialize_document(document, history.get(document.id, ())) for document in page],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=KnowledgeSearchPage)
async def search_documents(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    knowledge_base_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeSearchPage:
    simple_config = literal_column("'simple'::regconfig")
    ts_query = func.websearch_to_tsquery(simple_config, q.strip())
    predicates = [
        DocumentChunk.organization_id == user.organization_id,
        KnowledgeBase.organization_id == user.organization_id,
        KnowledgeBase.status == "active",
        KnowledgeDocument.status == "ready",
        KnowledgeDocument.deleted_at.is_(None),
        func.to_tsvector(simple_config, DocumentChunk.content).op("@@")(ts_query),
    ]
    if knowledge_base_id:
        await _resolve_knowledge_base(
            db, user.organization_id, knowledge_base_id, require_active=True
        )
        predicates.append(KnowledgeDocument.knowledge_base_id == knowledge_base_id)
    base = (
        select(DocumentChunk, KnowledgeDocument.name, KnowledgeBase.name)
        .join(
            KnowledgeDocument,
            (KnowledgeDocument.organization_id == DocumentChunk.organization_id)
            & (KnowledgeDocument.id == DocumentChunk.document_id),
        )
        .join(
            KnowledgeBase,
            (KnowledgeBase.organization_id == KnowledgeDocument.organization_id)
            & (KnowledgeBase.id == KnowledgeDocument.knowledge_base_id),
        )
        .where(*predicates)
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rank = func.ts_rank(func.to_tsvector(simple_config, DocumentChunk.content), ts_query)
    rows = (
        await db.execute(
            base.order_by(rank.desc(), DocumentChunk.document_id, DocumentChunk.chunk_index)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return KnowledgeSearchPage(
        items=[
            KnowledgeSearchResult(
                document_id=chunk.document_id,
                document_name=name,
                knowledge_base_name=base_name,
                chunk_index=chunk.chunk_index,
                excerpt=re.sub(r"\s+", " ", chunk.content).strip()[:320],
            )
            for chunk, name, base_name in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{document_id}", response_model=KnowledgeDocumentOut)
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeDocumentOut:
    document = await db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.organization_id == user.organization_id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return await document_out(db, document)


@router.get("/{document_id}/source-preview", response_model=KnowledgeSourcePreviewOut)
async def preview_document_source(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeSourcePreviewOut:
    document = await db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.organization_id == user.organization_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.content_type not in {"text/plain", "text/markdown"}:
        raise HTTPException(status_code=415, detail="Source preview is available for text and Markdown documents")

    preview_bytes = await db.scalar(
        select(
            func.substring(
                KnowledgeDocumentSource.content,
                1,
                SOURCE_PREVIEW_MAX_BYTES + 1,
            )
        ).where(
            KnowledgeDocumentSource.organization_id == user.organization_id,
            KnowledgeDocumentSource.document_id == document.id,
        )
    )
    if preview_bytes is None:
        raise HTTPException(status_code=410, detail="The retained source file is no longer available")
    truncated = len(preview_bytes) > SOURCE_PREVIEW_MAX_BYTES
    content = bytes(preview_bytes[:SOURCE_PREVIEW_MAX_BYTES]).decode("utf-8", errors="replace")
    return KnowledgeSourcePreviewOut(
        content=content,
        truncated=truncated,
        max_bytes=SOURCE_PREVIEW_MAX_BYTES,
    )


@router.put("/{document_id}/knowledge-base", response_model=KnowledgeDocumentOut)
async def move_document_to_knowledge_base(
    document_id: UUID,
    data: KnowledgeDocumentMove,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeDocumentOut:
    """Move an idle document while preserving its source, chunks, and job history."""
    document = await db.scalar(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.organization_id == user.organization_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    target = await db.scalar(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.id == data.knowledge_base_id,
            KnowledgeBase.organization_id == user.organization_id,
        )
        .with_for_update()
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if target.status != "active":
        raise HTTPException(status_code=409, detail="Documents can only be moved into an active knowledge base")
    if document.knowledge_base_id == target.id:
        return await document_out(db, document)
    if document.status in ("queued", "processing"):
        raise HTTPException(status_code=409, detail="Wait for document processing to finish before moving it")

    active_job = await db.scalar(
        select(DocumentIngestionJob.id)
        .where(
            DocumentIngestionJob.organization_id == user.organization_id,
            DocumentIngestionJob.document_id == document.id,
            DocumentIngestionJob.status.in_(("queued", "running")),
        )
        .with_for_update()
    )
    if active_job is not None:
        raise HTTPException(status_code=409, detail="Wait for document processing to finish before moving it")

    source_base_id = document.knowledge_base_id
    document.knowledge_base_id = target.id
    await db.flush()
    move_details = {
        "document_id": str(document.id),
        "from_knowledge_base_id": str(source_base_id),
        "to_knowledge_base_id": str(target.id),
    }
    for base_id in (source_base_id, target.id):
        record_knowledge_base_audit(
            db,
            organization_id=user.organization_id,
            knowledge_base_id=base_id,
            actor_user_id=user.id,
            event_type="document_moved",
            details=move_details,
        )
    return await document_out(db, document)


@router.post("/{document_id}/reprocess", response_model=KnowledgeDocumentOut, status_code=202)
async def reprocess_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> KnowledgeDocumentOut:
    document = await db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.organization_id == user.organization_id,
            KnowledgeDocument.deleted_at.is_(None),
        ).with_for_update()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.status == "failed":
        latest_error = await db.scalar(
            select(DocumentIngestionJob.last_error)
            .where(
                DocumentIngestionJob.organization_id == user.organization_id,
                DocumentIngestionJob.document_id == document.id,
            )
            .order_by(DocumentIngestionJob.created_at.desc(), DocumentIngestionJob.id.desc())
            .limit(1)
        )
        if requires_replacement(latest_error):
            raise HTTPException(status_code=409, detail="Upload a corrected file before processing again")
    source = await db.get(KnowledgeDocumentSource, (user.organization_id, document.id))
    if source is None:
        raise HTTPException(status_code=409, detail="Source artifact was cleaned up; upload the document again")
    active_job = await db.scalar(
        select(DocumentIngestionJob.id)
        .where(
            DocumentIngestionJob.organization_id == user.organization_id,
            DocumentIngestionJob.document_id == document.id,
            DocumentIngestionJob.status.in_(("queued", "running")),
        )
        .with_for_update()
    )
    if active_job is not None:
        raise HTTPException(status_code=409, detail="Document ingestion is already queued or running")
    db.add(
        DocumentIngestionJob(
            organization_id=user.organization_id,
            document_id=document.id,
            correlation_id=current_correlation_id(),
        )
    )
    document.status = "queued"
    await db.flush()
    record_knowledge_base_audit(
        db,
        organization_id=user.organization_id,
        knowledge_base_id=document.knowledge_base_id,
        actor_user_id=user.id,
        event_type="document_reprocessed",
        details={"document_id": str(document.id)},
    )
    return await document_out(db, document)


@router.delete("/{document_id}", status_code=204, responses={204: {"description": "Searchable content removed; document metadata and ingestion history retained"}})
async def delete_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> Response:
    document = await db.scalar(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.organization_id == user.organization_id,
        )
        .with_for_update()
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if document.deleted_at is not None:
        return Response(status_code=204)
    now = datetime.now(UTC)
    document.deleted_at = now
    record_knowledge_base_audit(
        db,
        organization_id=user.organization_id,
        knowledge_base_id=document.knowledge_base_id,
        actor_user_id=user.id,
        event_type="document_deleted",
        details={"document_id": str(document.id)},
    )
    await db.execute(
        update(DocumentIngestionJob)
        .where(
            DocumentIngestionJob.organization_id == user.organization_id,
            DocumentIngestionJob.document_id == document_id,
            DocumentIngestionJob.status.in_(("queued", "running")),
        )
        .values(
            status="cancelled",
            completed_at=now,
            last_error="Document removed by a workspace administrator",
        )
    )
    await db.execute(
        delete(KnowledgeDocumentSource).where(
            KnowledgeDocumentSource.organization_id == user.organization_id,
            KnowledgeDocumentSource.document_id == document_id,
        )
    )
    await db.execute(
        delete(DocumentChunk).where(
            DocumentChunk.organization_id == user.organization_id,
            DocumentChunk.document_id == document_id,
        )
    )
    return Response(status_code=204)


async def _resolve_knowledge_base(
    db: AsyncSession,
    organization_id: UUID,
    knowledge_base_id: UUID | None,
    *,
    require_active: bool = False,
) -> KnowledgeBase:
    predicate = [KnowledgeBase.organization_id == organization_id]
    if knowledge_base_id is None:
        predicate.append(KnowledgeBase.is_default.is_(True))
    else:
        predicate.append(KnowledgeBase.id == knowledge_base_id)
    base = await db.scalar(select(KnowledgeBase).where(*predicate))
    if base is None:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    if require_active and base.status != "active":
        raise HTTPException(status_code=409, detail="Archived knowledge bases are unavailable for this operation")
    return base
