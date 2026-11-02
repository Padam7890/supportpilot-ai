"""Human-approved commerce action job adapter."""

from uuid import UUID

from app.services.commerce_action_worker import claim_commerce_action, process_commerce_action
from app.workers.application.contracts import ClaimedJob, JobHandler


class CommerceActionHandler(JobHandler):
    kind = "commerce"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        job_id = await claim_commerce_action(organization_id)
        return ClaimedJob(self.kind, organization_id, job_id) if job_id else None

    async def process(self, job: ClaimedJob) -> None:
        assert job.job_id is not None
        await process_commerce_action(job.organization_id, job.job_id)
