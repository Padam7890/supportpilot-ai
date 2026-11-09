"""Application helpers for versioned, document-scoped embedding jobs."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.ai.infrastructure.embedding_gateway import is_embedding_provider_configured
from app.models import DocumentEmbeddingJob


async def enqueue_document_embeddings(
    db: AsyncSession,
    *,
    organization_id: UUID,
    document_id: UUID,
    correlation_id: str | None = None,
) -> UUID | None:
    """Queue/requeue embeddings for the configured model without duplicate jobs."""
    if not is_embedding_provider_configured():
        return None

    model = settings.ai_embedding_model
    if not model:
        return None
    job = await db.scalar(
        select(DocumentEmbeddingJob)
        .where(
            DocumentEmbeddingJob.organization_id == organization_id,
            DocumentEmbeddingJob.document_id == document_id,
            DocumentEmbeddingJob.embedding_model == model,
            DocumentEmbeddingJob.embedding_version == settings.ai_embedding_version,
        )
        .with_for_update()
    )
    now = datetime.now(UTC)
    if job is None:
        job = DocumentEmbeddingJob(
            organization_id=organization_id,
            document_id=document_id,
            correlation_id=correlation_id,
            embedding_model=model,
            embedding_version=settings.ai_embedding_version,
            dimensions=settings.ai_embedding_dimensions,
            status="queued",
            attempt_count=0,
            max_attempts=3,
            next_attempt_at=now,
        )
        db.add(job)
        await db.flush()
        return job.id
    if job.status == "running":
        return job.id
    job.status = "queued"
    job.attempt_count = 0
    job.dimensions = settings.ai_embedding_dimensions
    job.correlation_id = correlation_id or job.correlation_id
    job.next_attempt_at = now
    job.started_at = None
    job.completed_at = None
    job.last_error_code = None
    await db.flush()
    return job.id
