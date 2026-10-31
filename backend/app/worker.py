"""PostgreSQL-backed document ingestion worker.

Jobs are claimed with SKIP LOCKED, persisted as running before processing, and
reclaimed after a lease expires if a worker process dies.
"""

import asyncio
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
    Organization,
)

logger = logging.getLogger(__name__)
LEASE_TIMEOUT = timedelta(minutes=5)
ORGANIZATION_BATCH_SIZE = 100
_organization_cursor: UUID | None = None
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


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
        job = await db.scalar(
            select(DocumentIngestionJob)
            .where(
                DocumentIngestionJob.organization_id == organization_id,
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
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            await db.rollback()
            return None
        job.status = "running"
        job.attempt_count += 1
        job.started_at = now
        job.last_error = None
        document_id = job.document_id
        job_id = job.id
        document = await db.get(KnowledgeDocument, document_id)
        if document:
            document.status = "processing"
        await db.commit()
        return job_id, document_id


async def fail_exhausted_leases(organization_id: UUID) -> bool:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        job = await db.scalar(
            select(DocumentIngestionJob)
            .where(
                DocumentIngestionJob.organization_id == organization_id,
                DocumentIngestionJob.status == "running",
                DocumentIngestionJob.attempt_count >= DocumentIngestionJob.max_attempts,
                DocumentIngestionJob.updated_at <= now - LEASE_TIMEOUT,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            await db.rollback()
            return False
        job.status = "failed"
        job.completed_at = now
        job.last_error = "Worker lease expired after the retry limit"
        document = await db.get(KnowledgeDocument, job.document_id)
        if document:
            document.status = "failed"
        await db.commit()
        return True


async def process_job(organization_id: UUID, job_id: UUID, document_id: UUID) -> None:
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
                )
            )
            source = await db.get(KnowledgeDocumentSource, (organization_id, document_id))
            if job is None or document is None or source is None:
                raise ValueError("Document source is unavailable for ingestion")
            if len(source.content) > MAX_UPLOAD_BYTES:
                raise ValueError("Document exceeds the processing size limit")
            chunks = make_chunks(extract_text(document.name, source.content))
            if not chunks:
                raise ValueError("No searchable text could be extracted")
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
        logger.exception("Document ingestion failed", extra={"job_id": str(job_id)})
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            job = await db.scalar(
                select(DocumentIngestionJob).where(
                    DocumentIngestionJob.id == job_id,
                    DocumentIngestionJob.organization_id == organization_id,
                )
            )
            document = await db.scalar(
                select(KnowledgeDocument).where(
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.organization_id == organization_id,
                )
            )
            if job is None:
                await db.rollback()
                return
            exhausted = job.attempt_count >= job.max_attempts
            now = datetime.now(UTC)
            job.status = "failed" if exhausted else "queued"
            job.last_error = f"{type(exc).__name__}: processing failed"[:500]
            job.completed_at = now if exhausted else None
            if not exhausted:
                job.next_attempt_at = now + timedelta(seconds=min(10 * 2 ** (job.attempt_count - 1), 300))
            if document:
                document.status = "failed" if exhausted else "queued"
            await db.commit()


async def process_next_job() -> bool:
    global _organization_cursor
    async with SessionLocal() as db:
        statement = (
            select(Organization.id)
            .where(Organization.approval_status == "approved")
            .order_by(Organization.id)
            .limit(ORGANIZATION_BATCH_SIZE)
        )
        if _organization_cursor is not None:
            statement = statement.where(Organization.id > _organization_cursor)
        organizations = list(await db.scalars(statement))
        if not organizations and _organization_cursor is not None:
            _organization_cursor = None
            statement = (
                select(Organization.id)
                .where(Organization.approval_status == "approved")
                .order_by(Organization.id)
                .limit(ORGANIZATION_BATCH_SIZE)
            )
            organizations = list(await db.scalars(statement))
    for organization_id in organizations:
        _organization_cursor = organization_id
        claimed = await claim_one(organization_id)
        if claimed:
            await process_job(organization_id, *claimed)
            return True
        if await fail_exhausted_leases(organization_id):
            return True
    if len(organizations) < ORGANIZATION_BATCH_SIZE:
        _organization_cursor = None
    return False


async def run_worker(poll_seconds: float = 1) -> None:
    logging.basicConfig(level=logging.INFO)
    while True:
        if not await process_next_job():
            await asyncio.sleep(poll_seconds)


if __name__ == "__main__":
    asyncio.run(run_worker())
