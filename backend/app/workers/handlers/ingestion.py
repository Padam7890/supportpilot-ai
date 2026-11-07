"""PostgreSQL-backed document ingestion job handler.

Jobs are claimed with SKIP LOCKED, persisted as running before processing, and
reclaimed after a lease expires if a worker process dies.
"""

import io
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pypdf import PdfReader
from sqlalchemy import and_, or_, select

from app.db.session import SessionLocal, set_tenant_context
from app.models import (
    DocumentChunk,
    DocumentIngestionJob,
    KnowledgeDocument,
    KnowledgeDocumentSource,
)
from app.workers.domain.retry_policy import retry_delay_seconds

logger = logging.getLogger(__name__)
LEASE_TIMEOUT = timedelta(minutes=5)
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
JOB_CANDIDATE_BATCH_SIZE = 100


def extract_text(name: str, content: bytes) -> str:
    if name.lower().endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError("Encrypted PDF files are not supported")
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    return content.decode("utf-8-sig").strip()


def make_chunks(text: str, *, size: int = 1200, overlap: int = 180) -> list[str]:
    normalized = " ".join(text.split())
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            boundary = normalized.rfind(" ", start + size // 2, end)
            if boundary > start:
                end = boundary
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


async def claim_one(organization_id: UUID) -> tuple[UUID, UUID] | None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        candidates = (
            await db.execute(
                select(DocumentIngestionJob.id, DocumentIngestionJob.document_id)
                .join(
                    KnowledgeDocument,
                    and_(
                        KnowledgeDocument.organization_id == DocumentIngestionJob.organization_id,
                        KnowledgeDocument.id == DocumentIngestionJob.document_id,
                    ),
                )
                .where(
                    DocumentIngestionJob.organization_id == organization_id,
                    KnowledgeDocument.deleted_at.is_(None),
                    DocumentIngestionJob.attempt_count < DocumentIngestionJob.max_attempts,
                    or_(
                        and_(
                            DocumentIngestionJob.status == "queued",
                            DocumentIngestionJob.next_attempt_at <= now,
                        ),
                        and_(
                            DocumentIngestionJob.status == "running",
                            DocumentIngestionJob.updated_at <= now - LEASE_TIMEOUT,
                        ),
                    ),
                )
                .order_by(DocumentIngestionJob.created_at, DocumentIngestionJob.id)
                .limit(JOB_CANDIDATE_BATCH_SIZE)
            )
        ).all()
        for job_id, document_id in candidates:
            document = await db.scalar(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.organization_id == organization_id,
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.deleted_at.is_(None),
                )
                .with_for_update(skip_locked=True)
            )
            if document is None:
                continue
            job = await db.scalar(
                select(DocumentIngestionJob)
                .where(
                    DocumentIngestionJob.id == job_id,
                    DocumentIngestionJob.organization_id == organization_id,
                )
                .with_for_update(skip_locked=True)
            )
            if job is None:
                continue
            can_claim = job.attempt_count < job.max_attempts and (
                (job.status == "queued" and job.next_attempt_at <= now)
                or (job.status == "running" and job.updated_at <= now - LEASE_TIMEOUT)
            )
            if not can_claim:
                continue
            job.status = "running"
            job.attempt_count += 1
            job.started_at = now
            job.last_error = None
            document.status = "processing"
            await db.commit()
            return job_id, document_id
        await db.rollback()
        return None


async def fail_exhausted_leases(organization_id: UUID) -> bool:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        candidates = (
            await db.execute(
                select(DocumentIngestionJob.id, DocumentIngestionJob.document_id)
                .where(
                    DocumentIngestionJob.organization_id == organization_id,
                    DocumentIngestionJob.status == "running",
                    DocumentIngestionJob.attempt_count >= DocumentIngestionJob.max_attempts,
                    DocumentIngestionJob.updated_at <= now - LEASE_TIMEOUT,
                )
                .order_by(DocumentIngestionJob.updated_at, DocumentIngestionJob.id)
                .limit(JOB_CANDIDATE_BATCH_SIZE)
            )
        ).all()
        for job_id, document_id in candidates:
            document = await db.scalar(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.organization_id == organization_id,
                    KnowledgeDocument.id == document_id,
                )
                .with_for_update(skip_locked=True)
            )
            if document is None:
                continue
            job = await db.scalar(
                select(DocumentIngestionJob)
                .where(
                    DocumentIngestionJob.id == job_id,
                    DocumentIngestionJob.organization_id == organization_id,
                )
                .with_for_update(skip_locked=True)
            )
            if (
                job is None
                or job.status != "running"
                or job.attempt_count < job.max_attempts
                or job.updated_at > now - LEASE_TIMEOUT
            ):
                continue
            if document.deleted_at is not None:
                job.status = "cancelled"
                job.completed_at = now
                job.last_error = "Document was removed during ingestion"
                await db.commit()
                return True
            job.status = "failed"
            job.completed_at = now
            job.last_error = "Worker lease expired after the retry limit"
            document.status = "failed"
            await db.commit()
            return True
        await db.rollback()
        return False


async def process_job(organization_id: UUID, job_id: UUID, document_id: UUID) -> None:
    correlation_id: str | None = None
    try:
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            job = await db.scalar(
                select(DocumentIngestionJob).where(
                    DocumentIngestionJob.id == job_id,
                    DocumentIngestionJob.organization_id == organization_id,
                    DocumentIngestionJob.status == "running",
                )
            )
            document = await db.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.organization_id == organization_id,
                    KnowledgeDocument.deleted_at.is_(None),
                )
            )
            source = await db.get(KnowledgeDocumentSource, (organization_id, document_id))
            if job is None:
                await db.rollback()
                return
            correlation_id = job.correlation_id
            if document is None:
                await db.rollback()
                return
            if source is None:
                raise ValueError("Document source is unavailable for ingestion")
            if len(source.content) > MAX_UPLOAD_BYTES:
                raise ValueError("Document exceeds the processing size limit")
            document_name = document.name
            source_content = bytes(source.content)
            await db.rollback()

        chunks = make_chunks(extract_text(document_name, source_content))
        if not chunks:
            raise ValueError("No searchable text could be extracted")

        # Recheck both rows under a stable lock order before publishing chunks.
        # Deletion locks the document first, then cancels jobs and removes source/chunks.
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            document = await db.scalar(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.organization_id == organization_id,
                    KnowledgeDocument.deleted_at.is_(None),
                )
                .with_for_update()
            )
            job = await db.scalar(
                select(DocumentIngestionJob)
                .where(
                    DocumentIngestionJob.id == job_id,
                    DocumentIngestionJob.organization_id == organization_id,
                )
                .with_for_update()
            )
            if job is None:
                await db.rollback()
                return
            if document is None or job.status != "running":
                if job.status == "running":
                    job.status = "cancelled"
                    job.completed_at = datetime.now(UTC)
                    job.last_error = "Document was removed during ingestion"
                    await db.commit()
                else:
                    await db.rollback()
                return
            await db.execute(
                DocumentChunk.__table__.delete().where(
                    DocumentChunk.organization_id == organization_id,
                    DocumentChunk.document_id == document_id,
                )
            )
            db.add_all(
                DocumentChunk(
                    organization_id=organization_id,
                    document_id=document_id,
                    chunk_index=index,
                    content=chunk,
                )
                for index, chunk in enumerate(chunks)
            )
            document.status = "ready"
            job.status = "succeeded"
            job.completed_at = datetime.now(UTC)
            job.last_error = None
            await db.commit()
    except Exception as exc:
        logger.exception(
            "Document ingestion failed",
            extra={
                "job_id": str(job_id),
                "organization_id": str(organization_id),
                "correlation_id": correlation_id,
                "error_type": type(exc).__name__,
            },
        )
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            document = await db.scalar(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.organization_id == organization_id,
                )
                .with_for_update()
            )
            job = await db.scalar(
                select(DocumentIngestionJob)
                .where(
                    DocumentIngestionJob.id == job_id,
                    DocumentIngestionJob.organization_id == organization_id,
                )
                .with_for_update()
            )
            if job is None or job.status != "running":
                await db.rollback()
                return
            if document is None or document.deleted_at is not None:
                job.status = "cancelled"
                job.completed_at = datetime.now(UTC)
                job.last_error = "Document was removed during ingestion"
                await db.commit()
                return
            exhausted = job.attempt_count >= job.max_attempts
            now = datetime.now(UTC)
            job.status = "failed" if exhausted else "queued"
            job.last_error = f"{type(exc).__name__}: processing failed"[:500]
            job.completed_at = now if exhausted else None
            if not exhausted:
                job.next_attempt_at = now + timedelta(
                    seconds=retry_delay_seconds(job.attempt_count, base_seconds=10, cap_seconds=300)
                )
            if document:
                document.status = "failed" if exhausted else "queued"
            await db.commit()
