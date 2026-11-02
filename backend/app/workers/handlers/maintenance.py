"""Maintenance adapter for expirations and exhausted worker leases."""

from uuid import UUID

from app.features.widgets.retention import purge_expired_order_verifications
from app.services.ai_worker import fail_exhausted_ai_leases
from app.services.commerce_action_worker import (
    expire_one_pending_action,
    fail_exhausted_action_leases,
)
from app.workers.application.contracts import ClaimedJob, JobHandler
from app.workers.handlers.ingestion import fail_exhausted_leases


class MaintenanceHandler(JobHandler):
    kind = "maintenance"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        checks = (
            ("widget_verification_retention", purge_expired_order_verifications),
            ("commerce_expiration", expire_one_pending_action),
            ("ai_lease_expired", fail_exhausted_ai_leases),
            ("ingestion_lease_expired", fail_exhausted_leases),
            ("commerce_lease_expired", fail_exhausted_action_leases),
        )
        for event_kind, check in checks:
            if await check(organization_id):
                return ClaimedJob(self.kind, organization_id, event_name=event_kind)
        return None

    async def process(self, job: ClaimedJob) -> None:
        return None
