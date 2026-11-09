import os
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.core.config import settings
from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.domain.content_hash import hash_chunk_text, hash_document_text
from app.models import DocumentChunk, DocumentEmbedding, DocumentEmbeddingJob, KnowledgeDocument
from app.workers.handlers import embeddings as embeddings_module
from tests.test_knowledge_integration import approved_workspace, bearer

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Embedding handler tests require isolated PostgreSQL",
)


@pytest.mark.anyio
async def test_process_job_skips_unchanged_chunks(client, monkeypatch):
    owner = await approved_workspace(client, "embed-skip")
    org_id = UUID(owner["user"]["organization_id"])
    user_id = UUID(owner["user"]["id"])
    headers = bearer(owner["access_token"])
    bases = (await client.get("/api/v1/knowledge/bases", headers=headers)).json()["items"]
    base_id = UUID(bases[0]["id"])
    excerpt = "Return window is fourteen days for unused items."
    revision = hash_document_text(excerpt)
    document_id = uuid4()

    async with SessionLocal() as db:
        await set_tenant_context(db, org_id)
        db.add(
            KnowledgeDocument(
                organization_id=org_id,
                id=document_id,
                knowledge_base_id=base_id,
                name="returns.txt",
                content_type="text/plain",
                size_bytes=len(excerpt),
                status="ready",
                uploaded_by_user_id=user_id,
                content_revision=revision,
            )
        )
        await db.flush()
        db.add(
            DocumentChunk(
                organization_id=org_id,
                document_id=document_id,
                chunk_index=0,
                content=excerpt,
                content_hash=hash_chunk_text(excerpt),
            )
        )
        job = DocumentEmbeddingJob(
            organization_id=org_id,
            document_id=document_id,
            expected_content_revision=revision,
            embedding_model=settings.ai_embedding_model or "text-embedding-3-small",
            embedding_version=settings.ai_embedding_version,
            dimensions=settings.ai_embedding_dimensions,
            status="running",
            attempt_count=1,
            max_attempts=3,
            worker_token="worker-test-token",
        )
        db.add(job)
        await db.flush()
        db.add(
            DocumentEmbedding(
                organization_id=org_id,
                document_id=document_id,
                chunk_index=0,
                embedding_model=job.embedding_model,
                embedding_version=job.embedding_version,
                dimensions=job.dimensions,
                embedding=[0.1] * job.dimensions,
            )
        )
        await db.commit()
        job_id = job.id

    embed_mock = AsyncMock()
    monkeypatch.setattr(embeddings_module, "embed_texts", embed_mock)
    await embeddings_module.process_job(org_id, job_id)
    embed_mock.assert_not_called()
