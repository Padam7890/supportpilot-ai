"""AI execution job adapter."""

from uuid import UUID

from app.services.ai_worker import claim_ai_execution, process_ai_execution
from app.workers.application.contracts import ClaimedJob, JobHandler


class AIExecutionHandler(JobHandler):
    kind = "ai"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        job_id = await claim_ai_execution(organization_id)
        return ClaimedJob(self.kind, organization_id, job_id) if job_id else None

    async def process(self, job: ClaimedJob) -> None:
        assert job.job_id is not None
        await process_ai_execution(job.organization_id, job.job_id)
