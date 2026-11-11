"""Fair dispatcher for the existing PostgreSQL-backed durable job families."""

import asyncio
import logging
import time
from collections import Counter
from collections.abc import Sequence
from datetime import timedelta
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.knowledge_gap_reconciliation import reconcile_organization
from app.services.catalog import enqueue_reconciliation
from app.workers.application.contracts import ClaimedJob, JobHandler
from app.workers.application.scheduler import FairScheduler
from app.workers.handlers.ai import AIExecutionHandler
from app.workers.handlers.automation import AutomationExecutionHandler
from app.workers.handlers.catalog import CatalogSyncHandler, CatalogWebhookHandler
from app.workers.handlers.commerce import CommerceActionHandler
from app.workers.handlers.embedding_jobs import DocumentEmbeddingHandler
from app.workers.handlers.ingestion_jobs import IngestionHandler
from app.workers.handlers.maintenance import MaintenanceHandler
from app.workers.handlers.notifications import NotificationHandler
from app.workers.handlers.outbound import OutboundDeliveryHandler
from app.workers.infrastructure.job_repository import DurableJobRepository

logger = logging.getLogger(__name__)
RECONCILIATION_INTERVAL = timedelta(hours=1)
RECONCILIATION_FAILURE_RETRY = timedelta(minutes=1)
DEAD_LETTER_REPORT_INTERVAL = timedelta(minutes=15)


def default_handlers() -> tuple[JobHandler, ...]:
    """Return the registered job families in their stable dispatch order."""
    return (
        CatalogWebhookHandler(),
        CatalogSyncHandler(),
        OutboundDeliveryHandler(),
        NotificationHandler(),
        CommerceActionHandler(),
        AutomationExecutionHandler(),
        IngestionHandler(),
        DocumentEmbeddingHandler(),
        AIExecutionHandler(),
        MaintenanceHandler(),
    )


class WorkerDispatcher:
    """Round-robin tenant and handler scheduling with bounded job execution."""

    def __init__(
        self,
        *,
        handlers: Sequence[JobHandler] | None = None,
        repository: DurableJobRepository | None = None,
        job_timeout_seconds: float = 110,
    ) -> None:
        if job_timeout_seconds <= 0:
            raise ValueError("job_timeout_seconds must be positive")
        self.handlers = tuple(handlers or default_handlers())
        if not self.handlers:
            raise ValueError("at least one durable job handler is required")
        self.repository = repository or DurableJobRepository()
        self.job_timeout_seconds = job_timeout_seconds
        self._dispatch_lock = asyncio.Lock()
        self.scheduler = FairScheduler()
        self._next_reconciliation_due: dict[UUID, float] = {}
        self._next_gap_review_due: dict[UUID, float] = {}
        self._next_dead_letter_report: dict[UUID, float] = {}
        self._metrics: Counter[tuple[str, str]] = Counter()

    async def dispatch_one(self) -> bool:
        """Claim and process a single job; return false when all queues are idle."""
        async with self._dispatch_lock:
            organizations = await self._organization_page()
            if not organizations:
                return False
            await self._reconcile_if_due(organizations)
            await self._reconcile_gap_reviews_if_due(organizations)
            for organization_id in organizations:
                await self._report_dead_letters_if_due(organization_id)
            claimed = await self._claim_fairly(organizations)
            if claimed is None:
                return False
        await self._process_claimed(claimed)
        return True

    async def _organization_page(self) -> list[UUID]:
        organizations = await self.repository.approved_organizations(
            self.scheduler.organization_cursor
        )
        if not organizations and self.scheduler.organization_cursor is not None:
            self.scheduler.reset_page()
            organizations = await self.repository.approved_organizations()
        return organizations

    async def _claim_fairly(self, organizations: list[UUID]) -> ClaimedJob | None:
        ordered_orgs = self.scheduler.organizations_after_cursor(organizations)
        handler_count = len(self.handlers)
        for organization_id in ordered_orgs:
            handler_indices = self.scheduler.handler_indices(handler_count)
            for handler_index in handler_indices:
                handler_index %= handler_count
                handler = self.handlers[handler_index]
                try:
                    job = await handler.claim(organization_id)
                except SQLAlchemyError as exc:
                    logger.warning(
                        "worker_claim_database_unavailable",
                        extra={
                            "job_kind": handler.kind,
                            "organization_id": str(organization_id),
                            "error_type": type(exc).__name__,
                        },
                    )
                    return None
                except Exception as exc:  # isolate a broken queue family from other durable queues
                    logger.exception(
                        "worker_claim_failed",
                        extra={
                            "job_kind": handler.kind,
                            "organization_id": str(organization_id),
                            "error_type": type(exc).__name__,
                        },
                    )
                    continue
                if job is None:
                    continue
                self.scheduler.claimed(organization_id, handler_index, handler_count)
                logger.info(
                    "worker_job_claimed",
                    extra={
                        "job_kind": job.kind,
                        "job_event": job.event_name,
                        "organization_id": str(job.organization_id),
                        "job_id": str(job.job_id) if job.job_id else None,
                        "correlation_id": job.correlation_id,
                    },
                )
                return job
            self.scheduler.checked_organization(organization_id, handler_count)
        return None

    async def _process_claimed(self, job: ClaimedJob) -> None:
        handler = next((item for item in self.handlers if item.kind == job.kind), None)
        if handler is None:
            logger.error("worker_handler_missing job_kind=%s", job.kind)
            return
        started = time.monotonic()
        self._record_metric(job.kind, "started")
        try:
            async with asyncio.timeout(self.job_timeout_seconds):
                await handler.process(job)
        except TimeoutError:
            self._record_metric(job.kind, "timeout", time.monotonic() - started)
            logger.error(
                "worker_job_timeout",
                extra={
                    "job_kind": job.kind,
                    "job_event": job.event_name,
                    "organization_id": str(job.organization_id),
                    "job_id": str(job.job_id) if job.job_id else None,
                    "correlation_id": job.correlation_id,
                    "timeout_seconds": self.job_timeout_seconds,
                },
            )
        except Exception as exc:  # lease expiry/retry state remains the durable recovery path
            self._record_metric(job.kind, "unhandled_error", time.monotonic() - started)
            logger.exception(
                "worker_job_unhandled_error",
                extra={
                    "job_kind": job.kind,
                    "job_event": job.event_name,
                    "organization_id": str(job.organization_id),
                    "job_id": str(job.job_id) if job.job_id else None,
                    "error_type": type(exc).__name__,
                    "correlation_id": job.correlation_id,
                },
            )
        else:
            self._record_metric(job.kind, "handler_returned", time.monotonic() - started)
            logger.info(
                "worker_job_handler_returned",
                extra={
                    "job_kind": job.kind,
                    "job_event": job.event_name,
                    "organization_id": str(job.organization_id),
                    "job_id": str(job.job_id) if job.job_id else None,
                    "duration_ms": round((time.monotonic() - started) * 1000),
                    "correlation_id": job.correlation_id,
                },
            )

    async def _reconcile_if_due(self, organizations: list[UUID]) -> None:
        now = time.monotonic()
        for organization_id in organizations:
            if now < self._next_reconciliation_due.get(organization_id, 0):
                continue
            try:
                job_enqueued = await enqueue_reconciliation(organization_id)
            except Exception as exc:
                self._next_reconciliation_due[organization_id] = (
                    now + RECONCILIATION_FAILURE_RETRY.total_seconds()
                )
                logger.exception(
                    "worker_catalog_reconciliation_schedule_failed",
                    extra={
                        "organization_id": str(organization_id),
                        "error_type": type(exc).__name__,
                        "retry_in_seconds": RECONCILIATION_FAILURE_RETRY.total_seconds(),
                    },
                )
                continue
            self._next_reconciliation_due[organization_id] = (
                now + RECONCILIATION_INTERVAL.total_seconds()
            )
            logger.log(
                logging.INFO if job_enqueued else logging.DEBUG,
                "worker_catalog_reconciliation_schedule_checked",
                extra={
                    "organization_id": str(organization_id),
                    "job_enqueued": job_enqueued,
                    "next_check_in_seconds": RECONCILIATION_INTERVAL.total_seconds(),
                },
            )

    async def _reconcile_gap_reviews_if_due(self, organizations: list[UUID]) -> None:
        """Periodic bounded tenant-scoped reconciliation, independent of dashboard reads."""
        now = time.monotonic()
        for organization_id in organizations:
            if now < self._next_gap_review_due.get(organization_id, 0):
                continue
            try:
                async with SessionLocal() as db:
                    await set_tenant_context(db, organization_id)
                    count = await reconcile_organization(db, organization_id, limit=100)
                    await db.commit()
                self._next_gap_review_due[organization_id] = now + (30 if count == 100 else 120)
            except Exception:
                self._next_gap_review_due[organization_id] = now + 60
                logger.exception("worker_knowledge_gap_reconciliation_failed", extra={
                    "organization_id": str(organization_id),
                })

    async def _report_dead_letters_if_due(self, organization_id: UUID) -> None:
        now = time.monotonic()
        if now < self._next_dead_letter_report.get(organization_id, 0):
            return
        self._next_dead_letter_report[organization_id] = (
            now + DEAD_LETTER_REPORT_INTERVAL.total_seconds()
        )
        try:
            counts = await self.repository.failed_job_counts(organization_id)
        except SQLAlchemyError as exc:
            logger.warning(
                "worker_dead_letter_metrics_failed organization_id=%s error_type=%s",
                organization_id,
                type(exc).__name__,
            )
            return
        nonzero = {kind: count for kind, count in counts.items() if count}
        if nonzero:
            logger.warning(
                "worker_dead_letter_counts",
                extra={"organization_id": str(organization_id), "queues": nonzero},
            )

    def _record_metric(self, kind: str, outcome: str, elapsed_seconds: float = 0) -> None:
        key = (kind, outcome)
        self._metrics[key] += 1
        logger.info(
            "worker_job_metric",
            extra={
                "job_kind": kind,
                "outcome": outcome,
                "count": self._metrics[key],
                "duration_ms": round(elapsed_seconds * 1000),
            },
        )
