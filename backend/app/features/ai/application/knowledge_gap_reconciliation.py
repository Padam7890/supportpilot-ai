"""Bounded background reconciliation of approved FAQ ingestion and embedding state."""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.knowledge_document import (
    DocumentChunk,
    DocumentEmbedding,
    DocumentEmbeddingJob,
    KnowledgeDocument,
)
from app.models.knowledge_gap_review import KnowledgeGapReview


async def reconcile_review(db: AsyncSession, record: KnowledgeGapReview) -> None:
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
    count = await db.scalar(select(func.count()).select_from(DocumentChunk).where(
        DocumentChunk.organization_id == record.organization_id,
        DocumentChunk.document_id == record.document_id,
    ))
    if not count:
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
    covered = await db.scalar(select(func.count(func.distinct(DocumentEmbedding.chunk_index))).where(
        DocumentEmbedding.organization_id == record.organization_id,
        DocumentEmbedding.document_id == record.document_id,
        DocumentEmbedding.embedding_model == settings.ai_embedding_model,
        DocumentEmbedding.embedding_version == settings.ai_embedding_version,
        DocumentEmbedding.embedding_version == job.embedding_version,
    ))
    record.status = "ready" if covered == count else "pending_embeddings"

async def reconcile_organization(db: AsyncSession, organization_id: UUID, *, limit: int = 100) -> int:
    """Safe to repeat; never automatically resolve or publish an unverified gap."""
    records = (await db.scalars(select(KnowledgeGapReview).where(
        KnowledgeGapReview.organization_id == organization_id,
        KnowledgeGapReview.status.in_(("pending_ingestion", "pending_embeddings")),
    ).order_by(KnowledgeGapReview.created_at).limit(limit).with_for_update(skip_locked=True))).all()
    for record in records:
        await reconcile_review(db, record)
    await db.flush()
    return len(records)
