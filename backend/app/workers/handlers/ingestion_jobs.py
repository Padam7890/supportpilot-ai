"""Document ingestion job adapter."""

from uuid import UUID

from app.workers.application.contracts import ClaimedJob, JobHandler
from app.workers.handlers.ingestion import claim_one, process_job


class IngestionHandler(JobHandler):
    kind = "ingestion"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        claimed = await claim_one(organization_id)
        if claimed is None:
            return None
        job_id, document_id = claimed
        return ClaimedJob(self.kind, organization_id, job_id, document_id)

    async def process(self, job: ClaimedJob) -> None:
        assert job.job_id is not None and job.related_id is not None
        await process_job(job.organization_id, job.job_id, job.related_id)
