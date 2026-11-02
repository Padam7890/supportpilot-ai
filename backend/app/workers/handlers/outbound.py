"""Provider-neutral outbound delivery outbox handler."""

from uuid import UUID

from app.integrations.messaging.worker import (
    claim_integration_delivery,
    process_integration_delivery,
)
from app.workers.application.contracts import ClaimedJob, JobHandler


class OutboundDeliveryHandler(JobHandler):
    kind = "outbound"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        job_id = await claim_integration_delivery(organization_id)
        return ClaimedJob(self.kind, organization_id, job_id) if job_id else None

    async def process(self, job: ClaimedJob) -> None:
        assert job.job_id is not None
        await process_integration_delivery(job.organization_id, job.job_id)
