"""Leased outbound delivery worker backed by PostgreSQL and provider adapters."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.db.session import SessionLocal, set_tenant_context
from app.integrations.core import (
    IntegrationCapability,
    IntegrationConnectionRef,
    IntegrationError,
    IntegrationErrorCode,
    IntegrationRegistry,
    MessagingCapability,
    OutboundMessage,
)
from app.integrations.messaging.service import retry_delay_seconds
from app.integrations.registry import build_integration_registry
from app.models import (
    Conversation,
    IntegrationConnection,
    IntegrationDeliveryJob,
    Message,
)

logger = logging.getLogger(__name__)
DELIVERY_LEASE = timedelta(minutes=3)


async def claim_integration_delivery(organization_id: UUID) -> UUID | None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        job = await db.scalar(
            select(IntegrationDeliveryJob)
            .where(
                IntegrationDeliveryJob.organization_id == organization_id,
                or_(
                    and_(
                        IntegrationDeliveryJob.status == "queued",
                        IntegrationDeliveryJob.next_attempt_at <= now,
                        IntegrationDeliveryJob.attempt_count < IntegrationDeliveryJob.max_attempts,
                    ),
                    and_(
                        IntegrationDeliveryJob.status == "running",
                        IntegrationDeliveryJob.lease_expires_at < now,
                    ),
                ),
            )
            .order_by(IntegrationDeliveryJob.created_at, IntegrationDeliveryJob.id)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            await db.rollback()
            return None
        if job.status == "running" and job.attempt_count >= job.max_attempts:
            job.status = "failed"
            job.last_error_code = "delivery_lease_expired"
            job.completed_at = now
            job.lease_expires_at = None
            message = await db.scalar(
                select(Message).where(
                    Message.organization_id == organization_id,
                    Message.id == job.message_id,
                )
            )
            if message is not None:
                message.delivery_status = "failed"
            await db.commit()
            return job.id
        job.attempt_count += 1
        job.status = "running"
        job.lease_expires_at = now + DELIVERY_LEASE
        await db.commit()
        return job.id


async def process_integration_delivery(
    organization_id: UUID,
    job_id: UUID,
    *,
    registry: IntegrationRegistry | None = None,
) -> bool:
    provider_registry = registry or build_integration_registry()
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        job = await db.scalar(
            select(IntegrationDeliveryJob)
            .where(
                IntegrationDeliveryJob.organization_id == organization_id,
                IntegrationDeliveryJob.id == job_id,
                IntegrationDeliveryJob.status == "running",
            )
            .with_for_update()
        )
        if job is None:
            await db.rollback()
            return False
        connection = await db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.organization_id == organization_id,
                IntegrationConnection.id == job.connection_id,
                IntegrationConnection.status == "connected",
            )
        )
        message = await db.scalar(
            select(Message).where(
                Message.organization_id == organization_id,
                Message.id == job.message_id,
            )
        )
        conversation = (
            await db.scalar(
                select(Conversation).where(
                    Conversation.organization_id == organization_id,
                    Conversation.id == message.conversation_id,
                    Conversation.integration_connection_id == job.connection_id,
                )
            )
            if message is not None
            else None
        )
        if connection is None or message is None or conversation is None:
            await _finish_failed(db, job, message, "delivery_target_unavailable")
            await db.commit()
            return True
        target = IntegrationConnectionRef(
            id=connection.id,
            organization_id=connection.organization_id,
            provider_id=connection.provider_id,
            external_account_id=connection.external_account_id,
        )
        external_conversation_id = conversation.external_conversation_id
        outbound = OutboundMessage(content=message.content, content_type=message.content_type)
        attempt = job.attempt_count
        stable_key = str(job.id)
        await db.commit()

    try:
        sender = provider_registry.get_capability(
            target.provider_id,
            IntegrationCapability.OUTBOUND_MESSAGING,
            MessagingCapability,
        )
        if external_conversation_id is None:
            raise IntegrationError(IntegrationErrorCode.PERMANENT_FAILURE, retryable=False)
        receipt = await sender.send_message(
            target,
            external_conversation_id=external_conversation_id,
            message=outbound,
            idempotency_key=stable_key,
        )
        if receipt.status == "failed":
            raise IntegrationError(
                IntegrationErrorCode.TRANSIENT_FAILURE,
                retryable=True,
                provider_code=receipt.provider_status,
            )
        if receipt.status == "unknown":
            raise IntegrationError(IntegrationErrorCode.TRANSIENT_FAILURE, retryable=True)
        await _finish_succeeded(organization_id, job_id, receipt.external_message_id, receipt.status)
        return True
    except IntegrationError as exc:
        await _finish_error(
            organization_id,
            job_id,
            attempt,
            error_code=exc.code.value,
            retryable=exc.retryable,
            retry_after_seconds=exc.retry_after_seconds,
        )
        return True
    except Exception as exc:  # noqa: BLE001 - isolate provider bugs and retry with a safe code.
        logger.warning(
            "integration_delivery_provider_failure organization_id=%s job_id=%s error_type=%s",
            organization_id,
            job_id,
            type(exc).__name__,
        )
        await _finish_error(
            organization_id,
            job_id,
            attempt,
            error_code="provider_unavailable",
            retryable=True,
        )
        return True


async def _finish_failed(db, job, message, error_code: str) -> None:
    job.status = "failed"
    job.last_error_code = error_code
    job.completed_at = datetime.now(UTC)
    job.lease_expires_at = None
    if message is not None:
        message.delivery_status = "failed"


async def _finish_succeeded(
    organization_id: UUID,
    job_id: UUID,
    provider_message_id: str | None,
    delivery_status: str,
) -> None:
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        job = await db.scalar(
            select(IntegrationDeliveryJob)
            .where(
                IntegrationDeliveryJob.organization_id == organization_id,
                IntegrationDeliveryJob.id == job_id,
            )
            .with_for_update()
        )
        if job is None or job.status != "running":
            await db.rollback()
            return
        message = await db.scalar(
            select(Message).where(
                Message.organization_id == organization_id,
                Message.id == job.message_id,
            )
        )
        job.status = "succeeded"
        job.provider_message_id = provider_message_id
        job.last_error_code = None
        job.completed_at = datetime.now(UTC)
        job.lease_expires_at = None
        if message is not None:
            message.delivery_status = delivery_status
            if provider_message_id:
                message.external_message_id = provider_message_id
        await db.commit()


async def _finish_error(
    organization_id: UUID,
    job_id: UUID,
    attempt: int,
    *,
    error_code: str,
    retryable: bool,
    retry_after_seconds: int | None = None,
) -> None:
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        job = await db.scalar(
            select(IntegrationDeliveryJob)
            .where(
                IntegrationDeliveryJob.organization_id == organization_id,
                IntegrationDeliveryJob.id == job_id,
            )
            .with_for_update()
        )
        if job is None or job.status != "running":
            await db.rollback()
            return
        message = await db.scalar(
            select(Message).where(
                Message.organization_id == organization_id,
                Message.id == job.message_id,
            )
        )
        now = datetime.now(UTC)
        should_retry = retryable and attempt < job.max_attempts
        job.status = "queued" if should_retry else "failed"
        job.last_error_code = error_code
        job.lease_expires_at = None
        job.completed_at = None if should_retry else now
        if should_retry:
            delay = retry_delay_seconds(attempt, retry_after_seconds=retry_after_seconds)
            job.next_attempt_at = now + timedelta(seconds=delay)
        elif message is not None:
            message.delivery_status = "failed"
        await db.commit()
