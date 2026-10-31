import re
from datetime import UTC, datetime
from pathlib import PurePath
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, literal_column, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import (
    DocumentChunk,
    DocumentIngestionJob,
    KnowledgeDocument,
    KnowledgeDocumentSource,
    User,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.knowledge import (
    IngestionJobOut,
    KnowledgeDocumentOut,
    KnowledgeDocumentPage,
    KnowledgeSearchPage,
    KnowledgeSearchResult,
)

router = APIRouter(prefix="/knowledge/documents", tags=["knowledge"], responses=COMMON_ERROR_RESPONSES)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}


async def document_out(db: AsyncSession, document: KnowledgeDocument) -> KnowledgeDocumentOut:
    jobs = await db.scalars(
        select(DocumentIngestionJob)
        .where(
            DocumentIngestionJob.organization_id == document.organization_id,
            DocumentIngestionJob.document_id == document.id,
        )
        .order_by(DocumentIngestionJob.created_at.desc(), DocumentIngestionJob.id.desc())
        .limit(20)
    )
    return KnowledgeDocumentOut(
        id=document.id,
        name=document.name,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        status=document.status,
        created_at=document.created_at,
        updated_at=document.updated_at,
        deleted_at=document.deleted_at,
        jobs=[IngestionJobOut.model_validate(job) for job in jobs],
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

    document = KnowledgeDocument(
        organization_id=user.organization_id,
        name=safe_name,
        content_type=expected_type,
        size_bytes=len(content),
        status="queued",
        uploaded_by_user_id=user.id,
    )
    db.add(document)
    await db.flush()
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
                status="queued",
            ),
        ]
    )
    await db.flush()
    return await document_out(db, document)


@router.get("", response_model=KnowledgeDocumentPage)
async def list_documents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeDocumentPage:
    total = await db.scalar(
        select(func.count()).select_from(KnowledgeDocument).where(
            KnowledgeDocument.organization_id == user.organization_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
    ) or 0
    documents = await db.scalars(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.organization_id == user.organization_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
        .order_by(KnowledgeDocument.created_at.desc(), KnowledgeDocument.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return KnowledgeDocumentPage(
        items=[await document_out(db, document) for document in documents],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/search", response_model=KnowledgeSearchPage)
async def search_documents(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> KnowledgeSearchPage:
    simple_config = literal_column("'simple'::regconfig")
    ts_query = func.websearch_to_tsquery(simple_config, q.strip())
    base = (
        select(DocumentChunk, KnowledgeDocument.name)
        .join(
            KnowledgeDocument,
            (KnowledgeDocument.organization_id == DocumentChunk.organization_id)
            & (KnowledgeDocument.id == DocumentChunk.document_id),
        )
        .where(
            DocumentChunk.organization_id == user.organization_id,
            KnowledgeDocument.status == "ready",
            KnowledgeDocument.deleted_at.is_(None),
            func.to_tsvector(simple_config, DocumentChunk.content).op("@@")(ts_query),
        )
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
                chunk_index=chunk.chunk_index,
                excerpt=re.sub(r"\s+", " ", chunk.content).strip()[:320],
            )
            for chunk, name in rows
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
    db.add(DocumentIngestionJob(organization_id=user.organization_id, document_id=document.id))
    document.status = "queued"
    await db.flush()
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
