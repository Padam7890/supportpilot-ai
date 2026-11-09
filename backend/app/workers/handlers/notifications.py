"""Notification outbox job adapter."""

from uuid import UUID

from app.features.notifications.infrastructure.worker import claim_notification_outbox, process_notification_outbox
from app.workers.application.contracts import ClaimedJob, JobHandler


class NotificationHandler(JobHandler):
    kind = "notification"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        job_id = await claim_notification_outbox(organization_id)
        return ClaimedJob(self.kind, organization_id, job_id) if job_id else None

    async def process(self, job: ClaimedJob) -> None:
        if job.job_id is None:
            return
        await process_notification_outbox(job.organization_id, job.job_id)
