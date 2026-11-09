"""Durable asynchronous document embedding worker handler."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.infrastructure.embedding_gateway import EmbeddingProviderError, embed_texts
from app.models import DocumentChunk, DocumentEmbedding, DocumentEmbeddingJob, KnowledgeDocument
from app.workers.domain.lease_policy import DOCUMENT_EMBEDDING_LEASE
from app.workers.domain.retry_policy import retry_delay_seconds

logger = logging.getLogger(__name__)
CLAIM_BATCH_SIZE = 100


async def claim_one(organization_id: UUID) -> UUID | None:
    now = datetime.now(UTC)
    worker_token = secrets.token_urlsafe(16)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        candidates = (
            await db.scalars(
                select(DocumentEmbeddingJob.id)
                .join(
                    KnowledgeDocument,
                    and_(
                        KnowledgeDocument.organization_id == DocumentEmbeddingJob.organization_id,
                        KnowledgeDocument.id == DocumentEmbeddingJob.document_id,
                    ),
                )
                .where(
                    DocumentEmbeddingJob.organization_id == organization_id,
                    KnowledgeDocument.status == "ready",
                    KnowledgeDocument.deleted_at.is_(None),
                    DocumentEmbeddingJob.attempt_count < DocumentEmbeddingJob.max_attempts,
                    or_(
                        and_(
                            DocumentEmbeddingJob.status == "queued",
                            DocumentEmbeddingJob.next_attempt_at <= now,
                        ),
                        and_(
                            DocumentEmbeddingJob.status == "running",
                            DocumentEmbeddingJob.updated_at <= now - DOCUMENT_EMBEDDING_LEASE,
                        ),
                    ),
                )
                .order_by(DocumentEmbeddingJob.created_at, DocumentEmbeddingJob.id)
                .limit(CLAIM_BATCH_SIZE)
            )
        ).all()
        for job_id in candidates:
            job = await db.scalar(
                select(DocumentEmbeddingJob)
                .where(
                    DocumentEmbeddingJob.organization_id == organization_id,
                    DocumentEmbeddingJob.id == job_id,
                )
                .with_for_update(skip_locked=True)
            )
            if job is None:
                continue
            is_claimable = job.attempt_count < job.max_attempts and (
                (job.status == "queued" and job.next_attempt_at <= now)
                or (job.status == "running" and job.updated_at <= now - DOCUMENT_EMBEDDING_LEASE)
            )
            if not is_claimable:
                continue
            job.status = "running"
            job.attempt_count += 1
            job.started_at = now
            job.completed_at = None
            job.last_error_code = None
            job.worker_token = worker_token
            await db.commit()
            return job.id
        await db.rollback()
    return None


async def process_job(organization_id: UUID, job_id: UUID) -> None:
    worker_token: str | None = None
    try:
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            job = await db.scalar(
                select(DocumentEmbeddingJob).where(
                    DocumentEmbeddingJob.organization_id == organization_id,
                    DocumentEmbeddingJob.id == job_id,
                    DocumentEmbeddingJob.status == "running",
                )
            )
            if job is None:
                await db.rollback()
                return
            worker_token = job.worker_token
            document_id = job.document_id
            model = job.embedding_model
            version = job.embedding_version
            dimensions = job.dimensions
            expected_revision = job.expected_content_revision
            correlation_id = job.correlation_id
            chunk_rows = list(
                (await db.execute(
                    select(DocumentChunk.chunk_index, DocumentChunk.content, DocumentChunk.content_hash)
                    .join(
                        KnowledgeDocument,
                        and_(
                            KnowledgeDocument.organization_id == DocumentChunk.organization_id,
                            KnowledgeDocument.id == DocumentChunk.document_id,
                        ),
                    )
                    .where(
                        DocumentChunk.organization_id == organization_id,
                        DocumentChunk.document_id == document_id,
                        KnowledgeDocument.status == "ready",
                        KnowledgeDocument.deleted_at.is_(None),
                    )
                    .order_by(DocumentChunk.chunk_index)
                )).all()
            )
            existing_rows = list(
                (await db.execute(
                    select(
                        DocumentEmbedding.chunk_index,
                        DocumentChunk.content_hash,
                        DocumentEmbedding.dimensions,
                    )
                    .join(
                        DocumentChunk,
                        and_(
                            DocumentChunk.organization_id == DocumentEmbedding.organization_id,
                            DocumentChunk.document_id == DocumentEmbedding.document_id,
                            DocumentChunk.chunk_index == DocumentEmbedding.chunk_index,
                        ),
                    )
                    .where(
                        DocumentEmbedding.organization_id == organization_id,
                        DocumentEmbedding.document_id == document_id,
                        DocumentEmbedding.embedding_model == model,
                        DocumentEmbedding.embedding_version == version,
                    )
                )).all()
            )
            await db.rollback()

        if not chunk_rows:
            raise EmbeddingProviderError("embedding_document_has_no_chunks", retryable=False)

        existing_by_index = {
            row.chunk_index: (row.content_hash, row.dimensions) for row in existing_rows
        }
        pending: list[tuple[int, str, str]] = []
        for chunk_index, content, content_hash in chunk_rows:
            prior = existing_by_index.get(chunk_index)
            if prior is not None and prior[0] == content_hash and prior[1] == dimensions:
                continue
            pending.append((chunk_index, content, content_hash))

        new_vectors: dict[int, list[float]] = {}
        batch_size = max(1, min(settings.ai_embedding_batch_size, 128))
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset : offset + batch_size]
            vectors = await embed_texts(
                [content for _, content, _ in batch], model=model, dimensions=dimensions
            )
            for (chunk_index, _, _), vector in zip(batch, vectors, strict=True):
                new_vectors[chunk_index] = vector.values

        current_indexes = {chunk_index for chunk_index, _, _ in chunk_rows}

        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            document = await db.scalar(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.organization_id == organization_id,
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.status == "ready",
                    KnowledgeDocument.deleted_at.is_(None),
                )
                .with_for_update()
            )
            job = await db.scalar(
                select(DocumentEmbeddingJob)
                .where(
                    DocumentEmbeddingJob.organization_id == organization_id,
                    DocumentEmbeddingJob.id == job_id,
                )
                .with_for_update()
            )
            if (
                document is None
                or job is None
                or job.status != "running"
                or job.worker_token != worker_token
            ):
                if job is not None and job.status == "running":
                    job.status = "cancelled"
                    job.completed_at = datetime.now(UTC)
                    job.worker_token = None
                await db.commit()
                return

            if (
                expected_revision is not None
                and document.content_revision != expected_revision
            ):
                job.status = "cancelled"
                job.completed_at = datetime.now(UTC)
                job.last_error_code = "stale_content_revision"
                job.worker_token = None
                await db.commit()
                return

            await db.execute(
                delete(DocumentEmbedding).where(
                    DocumentEmbedding.organization_id == organization_id,
                    DocumentEmbedding.document_id == document_id,
                    DocumentEmbedding.embedding_model == model,
                    DocumentEmbedding.embedding_version == version,
                    DocumentEmbedding.chunk_index.not_in(current_indexes),
                )
            )
            if new_vectors:
                await db.execute(
                    delete(DocumentEmbedding).where(
                        DocumentEmbedding.organization_id == organization_id,
                        DocumentEmbedding.document_id == document_id,
                        DocumentEmbedding.embedding_model == model,
                        DocumentEmbedding.embedding_version == version,
                        DocumentEmbedding.chunk_index.in_(new_vectors.keys()),
                    )
                )
                db.add_all(
                    DocumentEmbedding(
                        organization_id=organization_id,
                        document_id=document_id,
                        chunk_index=chunk_index,
                        embedding_model=model,
                        embedding_version=version,
                        dimensions=dimensions,
                        embedding=values,
                    )
                    for chunk_index, values in new_vectors.items()
                )

            job.status = "succeeded"
            job.completed_at = datetime.now(UTC)
            job.last_error_code = None
            job.worker_token = None
            await db.commit()
            logger.info(
                "document_embeddings_succeeded",
                extra={
                    "organization_id": str(organization_id),
                    "document_id": str(document_id),
                    "job_id": str(job_id),
                    "correlation_id": correlation_id,
                    "embedding_model": model,
                    "chunk_count": len(chunk_rows),
                    "embedded_count": len(new_vectors),
                    "skipped_count": len(chunk_rows) - len(pending),
                },
            )
    except EmbeddingProviderError as exc:
        await _record_failure(organization_id, job_id, exc.code, retryable=exc.retryable, worker_token=worker_token)
    except (SQLAlchemyError, TimeoutError, ValueError, TypeError, OSError) as exc:
        logger.error(
            "document_embeddings_failed_unexpectedly",
            extra={
                "organization_id": str(organization_id),
                "job_id": str(job_id),
                "error_type": type(exc).__name__,
            },
        )
        await _record_failure(
            organization_id, job_id, "embedding_internal_failure", retryable=True, worker_token=worker_token
        )


async def _record_failure(
    organization_id: UUID,
    job_id: UUID,
    code: str,
    *,
    retryable: bool,
    worker_token: str | None,
) -> None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        job = await db.scalar(
            select(DocumentEmbeddingJob)
            .where(
                DocumentEmbeddingJob.organization_id == organization_id,
                DocumentEmbeddingJob.id == job_id,
            )
            .with_for_update()
        )
        if job is None or job.status != "running" or (worker_token and job.worker_token != worker_token):
            await db.rollback()
            return
        terminal = not retryable or job.attempt_count >= job.max_attempts
        job.status = "failed" if terminal else "queued"
        job.last_error_code = code[:80]
        job.completed_at = now if terminal else None
        job.worker_token = None if terminal else job.worker_token
        if not terminal:
            job.next_attempt_at = now + timedelta(
                seconds=retry_delay_seconds(job.attempt_count, base_seconds=10, cap_seconds=300)
            )
        await db.commit()
        logger.warning(
            "document_embeddings_attempt_failed",
            extra={
                "organization_id": str(organization_id),
                "job_id": str(job_id),
                "document_id": str(job.document_id),
                "correlation_id": job.correlation_id,
                "error_code": code,
                "attempt": job.attempt_count,
                "terminal": terminal,
            },
        )
