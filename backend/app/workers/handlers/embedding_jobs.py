"""Durable embedding-job dispatcher adapter."""

from uuid import UUID

from app.workers.application.contracts import ClaimedJob, JobHandler
from app.workers.handlers.embeddings import claim_one, process_job


class DocumentEmbeddingHandler(JobHandler):
    kind = "document_embedding"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        job_id = await claim_one(organization_id)
        return ClaimedJob(self.kind, organization_id, job_id) if job_id else None

    async def process(self, job: ClaimedJob) -> None:
        assert job.job_id is not None
        await process_job(job.organization_id, job.job_id)
