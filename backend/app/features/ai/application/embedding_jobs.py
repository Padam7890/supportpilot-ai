"""Application helpers for versioned, document-scoped embedding jobs."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.ai.domain.content_hash import PENDING_CONTENT_REVISION
from app.features.ai.infrastructure.embedding_gateway import is_embedding_provider_configured
from app.models import DocumentEmbeddingJob, KnowledgeDocument


async def enqueue_document_embeddings(
    db: AsyncSession,
    *,
    organization_id: UUID,
    document_id: UUID,
    correlation_id: str | None = None,
    expected_content_revision: str | None = None,
) -> UUID | None:
    """Queue or refresh embeddings for the configured model and content revision."""
    if not is_embedding_provider_configured():
        return None

    model = settings.ai_embedding_model
    if not model:
        return None

    document = await db.scalar(
        select(KnowledgeDocument).where(
            KnowledgeDocument.organization_id == organization_id,
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.deleted_at.is_(None),
        )
    )
    if document is None or document.status != "ready":
        return None

    revision = expected_content_revision or document.content_revision
    if revision == PENDING_CONTENT_REVISION:
        return None

    dimensions = settings.ai_embedding_dimensions
    now = datetime.now(UTC)
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

    if job is None:
        job = DocumentEmbeddingJob(
            organization_id=organization_id,
            document_id=document_id,
            correlation_id=correlation_id,
            expected_content_revision=revision,
            embedding_model=model,
            embedding_version=settings.ai_embedding_version,
            dimensions=dimensions,
            status="queued",
            attempt_count=0,
            max_attempts=3,
            next_attempt_at=now,
        )
        db.add(job)
        await db.flush()
        return job.id

    if job.status == "running" and job.expected_content_revision == revision:
        return job.id

    if (
        job.status == "succeeded"
        and job.expected_content_revision == revision
        and job.dimensions == dimensions
    ):
        return job.id

    if job.status == "running" and job.expected_content_revision != revision:
        job.status = "cancelled"
        job.completed_at = now
        job.last_error_code = "stale_content_revision"
        job.worker_token = None

    reset_attempts = job.status != "succeeded" or job.expected_content_revision != revision
    job.status = "queued"
    job.expected_content_revision = revision
    job.dimensions = dimensions
    job.correlation_id = correlation_id or job.correlation_id
    job.next_attempt_at = now
    job.worker_token = None
    if reset_attempts:
        job.attempt_count = 0
    job.started_at = None
    job.completed_at = None
    job.last_error_code = None
    await db.flush()
    return job.id
