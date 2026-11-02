"""Read-only worker scheduling and tenant-scoped dead-letter visibility."""

from uuid import UUID

from sqlalchemy import func, select

from app.db.session import SessionLocal, set_tenant_context
from app.models import (
    AIExecution,
    CatalogSyncJob,
    CatalogWebhookEvent,
    CommerceAction,
    DocumentIngestionJob,
    IntegrationDeliveryJob,
    Organization,
)

ORGANIZATION_PAGE_SIZE = 100


class DurableJobRepository:
    """Coordinates reads across existing durable job tables; claims stay feature-local."""

    async def approved_organizations(self, after: UUID | None = None) -> list[UUID]:
        async with SessionLocal() as db:
            statement = (
                select(Organization.id)
                .where(Organization.approval_status == "approved")
                .order_by(Organization.id)
                .limit(ORGANIZATION_PAGE_SIZE)
            )
            if after is not None:
                statement = statement.where(Organization.id > after)
            return list(await db.scalars(statement))

    async def failed_job_counts(self, organization_id: UUID) -> dict[str, int]:
        """Count persisted terminal failures for one tenant, honoring RLS context."""
        counts: dict[str, int] = {}
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            count_queries = {
                "ai": select(func.count())
                .select_from(AIExecution)
                .where(
                    AIExecution.organization_id == organization_id,
                    AIExecution.status == "failed",
                ),
                "catalog": select(func.count())
                .select_from(CatalogSyncJob)
                .where(
                    CatalogSyncJob.organization_id == organization_id,
                    CatalogSyncJob.status == "failed",
                ),
                "catalog_webhook": select(func.count())
                .select_from(CatalogWebhookEvent)
                .where(
                    CatalogWebhookEvent.organization_id == organization_id,
                    CatalogWebhookEvent.status == "failed",
                ),
                "ingestion": select(func.count())
                .select_from(DocumentIngestionJob)
                .where(
                    DocumentIngestionJob.organization_id == organization_id,
                    DocumentIngestionJob.status == "failed",
                ),
                "commerce": select(func.count())
                .select_from(CommerceAction)
                .where(
                    CommerceAction.organization_id == organization_id,
                    CommerceAction.execution_status == "failed",
                ),
                "outbound": select(func.count())
                .select_from(IntegrationDeliveryJob)
                .where(
                    IntegrationDeliveryJob.organization_id == organization_id,
                    IntegrationDeliveryJob.status == "failed",
                ),
            }
            for kind, statement in count_queries.items():
                counts[kind] = int(await db.scalar(statement) or 0)
            await db.rollback()
        return counts
