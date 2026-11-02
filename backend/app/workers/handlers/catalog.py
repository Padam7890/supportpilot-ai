"""Catalog sync and verified webhook job adapters."""

from uuid import UUID

from app.services.catalog import (
    claim_catalog_job,
    claim_catalog_webhook,
    process_catalog_webhook,
    resolve_shopify_credentials,
    run_catalog_sync_page,
)
from app.workers.application.contracts import ClaimedJob, JobHandler


class CatalogWebhookHandler(JobHandler):
    kind = "catalog_webhook"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        job_id = await claim_catalog_webhook(organization_id)
        return ClaimedJob(self.kind, organization_id, job_id) if job_id else None

    async def process(self, job: ClaimedJob) -> None:
        assert job.job_id is not None
        await process_catalog_webhook(
            job.organization_id,
            job.job_id,
            resolve_credentials=resolve_shopify_credentials,
        )


class CatalogSyncHandler(JobHandler):
    kind = "catalog_sync"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        job_id = await claim_catalog_job(organization_id)
        return ClaimedJob(self.kind, organization_id, job_id) if job_id else None

    async def process(self, job: ClaimedJob) -> None:
        assert job.job_id is not None
        await run_catalog_sync_page(
            job.organization_id,
            job.job_id,
            resolve_credentials=resolve_shopify_credentials,
        )
