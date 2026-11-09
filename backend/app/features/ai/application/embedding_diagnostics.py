"""Embedding coverage diagnostics for knowledge documents."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.features.ai.infrastructure.embedding_gateway import is_embedding_provider_configured
from app.models import DocumentChunk, DocumentEmbedding, DocumentEmbeddingJob


async def document_embedding_diagnostics(
    db: AsyncSession,
    *,
    organization_id: UUID,
    document_id: UUID,
) -> dict[str, object]:
    chunk_count = int(
        (
            await db.execute(
                select(func.count())
                .select_from(DocumentChunk)
                .where(
                    DocumentChunk.organization_id == organization_id,
                    DocumentChunk.document_id == document_id,
                )
            )
        ).scalar_one()
        or 0
    )
    embedded_count = 0
    coverage: float | None = None
    if is_embedding_provider_configured() and settings.ai_embedding_model and chunk_count:
        embedded_count = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(DocumentEmbedding)
                    .where(
                        DocumentEmbedding.organization_id == organization_id,
                        DocumentEmbedding.document_id == document_id,
                        DocumentEmbedding.embedding_model == settings.ai_embedding_model,
                        DocumentEmbedding.embedding_version == settings.ai_embedding_version,
                        DocumentEmbedding.dimensions == settings.ai_embedding_dimensions,
                    )
                )
            ).scalar_one()
            or 0
        )
        coverage = round(embedded_count / chunk_count, 4)

    job = await db.scalar(
        select(DocumentEmbeddingJob)
        .where(
            DocumentEmbeddingJob.organization_id == organization_id,
            DocumentEmbeddingJob.document_id == document_id,
            DocumentEmbeddingJob.embedding_model == settings.ai_embedding_model,
            DocumentEmbeddingJob.embedding_version == settings.ai_embedding_version,
        )
        .order_by(DocumentEmbeddingJob.updated_at.desc())
    )
    return {
        "chunk_count": chunk_count,
        "embedded_chunk_count": embedded_count,
        "coverage": coverage,
        "latest_job_status": job.status if job else None,
        "latest_job_error_code": job.last_error_code if job else None,
        "embedding_model": settings.ai_embedding_model,
        "embedding_version": settings.ai_embedding_version,
    }
