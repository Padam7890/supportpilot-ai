"""Tenant-scoped management APIs for concrete integration connections."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.integrations.connections.service import (
    disconnect_generic_connection,
    record_connection_audit,
)
from app.integrations.core.errors.integration import IntegrationError
from app.integrations.core.registry import IntegrationRegistry
from app.integrations.core.types import IntegrationCapability
from app.models import (
    AIAgent,
    CatalogWebhookEvent,
    IntegrationConnection,
    IntegrationConnectionAudit,
    IntegrationDeliveryJob,
    IntegrationWebhookEvent,
    ShopifyAccessAudit,
    User,
)
from app.schemas.integrations import (
    IntegrationConnectionAuditPageOut,
    IntegrationConnectionEventOut,
    IntegrationConnectionListOut,
    IntegrationConnectionOut,
    IntegrationConnectionRoutingUpdate,
    IntegrationDeliveryPageOut,
    IntegrationDeliveryRetryOut,
    IntegrationProviderOut,
    IntegrationWebhookEventOut,
    IntegrationWebhookEventPageOut,
    IntegrationWebhookRetryOut,
    ShopifyAccessAuditPageOut,
)

router = APIRouter(prefix="/integrations", tags=["Integration management"])
logger = logging.getLogger(__name__)


@router.get(
    "/connections/{connection_id}/audit",
    response_model=IntegrationConnectionAuditPageOut,
)
async def list_connection_audit(
    connection_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> IntegrationConnectionAuditPageOut:
    """Return secret-free lifecycle history for a tenant-owned connection."""
    _validate_pagination(limit, offset)
    await _require_connection(db, user.organization_id, connection_id)
    filters = (
        IntegrationConnectionAudit.organization_id == user.organization_id,
        IntegrationConnectionAudit.connection_id == connection_id,
    )
    total = await db.scalar(
        select(func.count()).select_from(IntegrationConnectionAudit).where(*filters)
    ) or 0
    rows = await db.execute(
        select(
            IntegrationConnectionAudit.id,
            IntegrationConnectionAudit.event_type,
            User.full_name.label("actor_name"),
            IntegrationConnectionAudit.provider_id,
            IntegrationConnectionAudit.details,
            IntegrationConnectionAudit.created_at,
        )
        .outerjoin(
            User,
            (User.organization_id == IntegrationConnectionAudit.organization_id)
            & (User.id == IntegrationConnectionAudit.actor_user_id),
        )
        .where(*filters)
        .order_by(IntegrationConnectionAudit.created_at.desc(), IntegrationConnectionAudit.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = []
    for row in rows.mappings():
        details = row["details"] if isinstance(row["details"], dict) else {}
        scopes = details.get("granted_scopes")
        items.append(
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "actor_name": row["actor_name"],
                "provider_id": row["provider_id"],
                "auth_mode": details.get("auth_mode") if isinstance(details.get("auth_mode"), str) else None,
                "granted_scopes": scopes if isinstance(scopes, list) and all(isinstance(scope, str) for scope in scopes) else [],
                "previous_ai_agent_id": details.get("previous_ai_agent_id"),
                "ai_agent_id": details.get("ai_agent_id"),
                "created_at": row["created_at"],
            }
        )
    return IntegrationConnectionAuditPageOut(items=items, total=int(total), limit=limit, offset=offset)


@router.get(
    "/connections/{connection_id}/access-audit",
    response_model=ShopifyAccessAuditPageOut,
)
async def list_shopify_access_audit(
    connection_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> ShopifyAccessAuditPageOut:
    """List safe order-access audit metadata for the tenant's connected Shopify store."""
    _validate_pagination(limit, offset)
    connection = await _require_connection(db, user.organization_id, connection_id)
    if connection.provider_id != "shopify":
        raise HTTPException(status_code=404, detail="Shopify access audit not found")

    filters = (
        ShopifyAccessAudit.organization_id == user.organization_id,
        ShopifyAccessAudit.details["shop_domain"].as_string() == connection.external_account_id,
    )
    total = await db.scalar(
        select(func.count()).select_from(ShopifyAccessAudit).where(*filters)
    ) or 0
    rows = await db.execute(
        select(
            ShopifyAccessAudit.id,
            User.full_name.label("actor_name"),
            ShopifyAccessAudit.resource_type,
            ShopifyAccessAudit.result_count,
            ShopifyAccessAudit.details,
            ShopifyAccessAudit.created_at,
        )
        .join(
            User,
            (User.organization_id == ShopifyAccessAudit.organization_id)
            & (User.id == ShopifyAccessAudit.user_id),
        )
        .where(*filters)
        .order_by(ShopifyAccessAudit.created_at.desc(), ShopifyAccessAudit.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = []
    for row in rows.mappings():
        details = row["details"] if isinstance(row["details"], dict) else {}
        raw_outcome = details.get("verification") or details.get("view")
        items.append(
            {
                "id": row["id"],
                "actor_name": row["actor_name"],
                "resource_type": row["resource_type"],
                "result_count": row["result_count"],
                "outcome": raw_outcome if isinstance(raw_outcome, str) else None,
                "created_at": row["created_at"],
            }
        )
    return ShopifyAccessAuditPageOut(items=items, total=int(total), limit=limit, offset=offset)


@router.get("/providers", response_model=list[IntegrationProviderOut])
async def list_integration_providers(request: Request) -> list[IntegrationProviderOut]:
    """Return only providers with a registered, real adapter."""
    registry: IntegrationRegistry = request.app.state.integration_registry
    return [
        IntegrationProviderOut(
            provider_id=provider.provider_id,
            display_name=provider.display_name,
            version=provider.version,
            capabilities=sorted(capability.value for capability in provider.capabilities),
        )
        for provider in registry.list_providers()
    ]


@router.get("/connections", response_model=IntegrationConnectionListOut)
async def list_connections(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IntegrationConnectionListOut:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Invalid pagination parameters")
    base = select(IntegrationConnection).where(
        IntegrationConnection.organization_id == user.organization_id
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = await db.scalars(
        base.order_by(IntegrationConnection.created_at.desc(), IntegrationConnection.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return IntegrationConnectionListOut(
        items=list(rows.all()),
        total=int(total or 0),
    )


@router.get("/connections/{connection_id}", response_model=IntegrationConnectionOut)
async def get_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IntegrationConnectionOut:
    connection = await db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.organization_id == user.organization_id,
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return IntegrationConnectionOut.model_validate(connection)


@router.patch(
    "/connections/{connection_id}/routing",
    response_model=IntegrationConnectionOut,
)
async def update_connection_bot_routing(
    connection_id: UUID,
    data: IntegrationConnectionRoutingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> IntegrationConnectionOut:
    """Set the bot for new inbound conversations on a capable provider connection."""
    connection = await db.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.organization_id == user.organization_id,
            IntegrationConnection.id == connection_id,
        )
        .with_for_update()
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")

    registry: IntegrationRegistry = request.app.state.integration_registry
    try:
        provider = registry.get_provider(connection.provider_id)
    except IntegrationError:
        raise HTTPException(status_code=409, detail="The provider is no longer available") from None
    if IntegrationCapability.INBOUND_MESSAGING not in provider.descriptor.capabilities:
        raise HTTPException(status_code=409, detail="This provider does not support inbound messaging")
    if connection.status != "connected":
        raise HTTPException(status_code=409, detail="Connect this provider before configuring bot routing")

    if data.ai_agent_id is not None:
        agent = await db.scalar(
            select(AIAgent).where(
                AIAgent.organization_id == user.organization_id,
                AIAgent.id == data.ai_agent_id,
                AIAgent.status == "active",
            )
        )
        if agent is None:
            raise HTTPException(status_code=404, detail="Active AI bot not found")

    previous_agent_id = connection.ai_agent_id
    if previous_agent_id != data.ai_agent_id:
        connection.ai_agent_id = data.ai_agent_id
        record_connection_audit(
            db,
            connection,
            event_type="bot_routing_changed",
            actor_user_id=user.id,
            previous_ai_agent_id=previous_agent_id,
            ai_agent_id=data.ai_agent_id,
        )
        await db.flush()
    return IntegrationConnectionOut.model_validate(connection)


@router.get(
    "/connections/{connection_id}/events",
    response_model=IntegrationWebhookEventPageOut,
)
async def list_connection_events(
    connection_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IntegrationWebhookEventPageOut:
    _validate_pagination(limit, offset)
    await _require_connection(db, user.organization_id, connection_id)

    filters = (
        IntegrationWebhookEvent.organization_id == user.organization_id,
        IntegrationWebhookEvent.connection_id == connection_id,
    )
    total = await db.scalar(
        select(func.count()).select_from(IntegrationWebhookEvent).where(*filters)
    ) or 0
    rows = await db.execute(
        select(
            IntegrationWebhookEvent.id,
            IntegrationWebhookEvent.provider_id,
            IntegrationWebhookEvent.event_type,
            IntegrationWebhookEvent.occurred_at,
            IntegrationWebhookEvent.created_at.label("received_at"),
            func.coalesce(CatalogWebhookEvent.status, "received").label("processing_status"),
            func.coalesce(CatalogWebhookEvent.attempt_count, 0).label("attempt_count"),
            CatalogWebhookEvent.last_error_code,
            CatalogWebhookEvent.correlation_id,
            func.coalesce(CatalogWebhookEvent.manual_retry_count, 0).label("manual_retry_count"),
        )
        .outerjoin(
            CatalogWebhookEvent,
            (CatalogWebhookEvent.organization_id == IntegrationWebhookEvent.organization_id)
            & (CatalogWebhookEvent.connection_id == IntegrationWebhookEvent.connection_id)
            & (CatalogWebhookEvent.provider_id == IntegrationWebhookEvent.provider_id)
            & (CatalogWebhookEvent.external_event_id == IntegrationWebhookEvent.external_event_id),
        )
        .where(*filters)
        .order_by(IntegrationWebhookEvent.created_at.desc(), IntegrationWebhookEvent.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return IntegrationWebhookEventPageOut(
        items=[
            IntegrationWebhookEventOut(
                **row,
                manual_retry_available=(
                    row["processing_status"] == "failed"
                    and row["manual_retry_count"] < 3
                ),
            )
            for row in rows.mappings()
        ],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/connections/{connection_id}/events/{event_id}/retry",
    response_model=IntegrationWebhookRetryOut,
)
async def retry_failed_webhook_event(
    connection_id: UUID,
    event_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> IntegrationWebhookRetryOut:
    """Requeue one previously verified failed Shopify catalog event."""
    connection = await _require_connection(db, user.organization_id, connection_id)
    if connection.provider_id != "shopify" or connection.status != "connected":
        raise HTTPException(status_code=409, detail="A connected Shopify connection is required")

    event = await db.scalar(
        select(CatalogWebhookEvent)
        .join(
            IntegrationWebhookEvent,
            (IntegrationWebhookEvent.organization_id == CatalogWebhookEvent.organization_id)
            & (IntegrationWebhookEvent.connection_id == CatalogWebhookEvent.connection_id)
            & (IntegrationWebhookEvent.provider_id == CatalogWebhookEvent.provider_id)
            & (IntegrationWebhookEvent.external_event_id == CatalogWebhookEvent.external_event_id),
        )
        .where(
            CatalogWebhookEvent.organization_id == user.organization_id,
            CatalogWebhookEvent.connection_id == connection_id,
            CatalogWebhookEvent.id == event_id,
            CatalogWebhookEvent.provider_id == "shopify",
        )
        .with_for_update(of=CatalogWebhookEvent)
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Webhook event not found")
    if event.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed events can be retried")
    if event.manual_retry_count >= 3:
        raise HTTPException(status_code=409, detail="Manual retry limit reached for this event")

    event.manual_retry_count += 1
    event.attempt_count = 0
    event.status = "queued"
    event.next_attempt_at = datetime.now(UTC)
    event.completed_at = None
    event.last_error_code = None
    logger.info(
        "integration_webhook_manual_retry_queued",
        extra={
            "organization_id": str(user.organization_id),
            "connection_id": str(connection_id),
            "event_id": str(event.id),
            "actor_user_id": str(user.id),
            "manual_retry_count": event.manual_retry_count,
        },
    )
    return IntegrationWebhookRetryOut(
        id=event.id,
        processing_status="queued",
        manual_retry_count=event.manual_retry_count,
        message="Webhook event queued for processing.",
    )


@router.get(
    "/connections/{connection_id}/deliveries",
    response_model=IntegrationDeliveryPageOut,
)
async def list_connection_deliveries(
    connection_id: UUID,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IntegrationDeliveryPageOut:
    _validate_pagination(limit, offset)
    await _require_connection(db, user.organization_id, connection_id)

    filters = (
        IntegrationDeliveryJob.organization_id == user.organization_id,
        IntegrationDeliveryJob.connection_id == connection_id,
    )
    total = await db.scalar(
        select(func.count()).select_from(IntegrationDeliveryJob).where(*filters)
    ) or 0
    rows = await db.scalars(
        select(IntegrationDeliveryJob)
        .where(*filters)
        .order_by(IntegrationDeliveryJob.created_at.desc(), IntegrationDeliveryJob.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return IntegrationDeliveryPageOut(
        items=[
            {
                "id": row.id,
                "message_id": row.message_id,
                "status": row.status,
                "attempt_count": row.attempt_count,
                "max_attempts": row.max_attempts,
                "manual_retry_count": row.manual_retry_count,
                "manual_retry_available": (
                    row.status == "failed" and row.manual_retry_count < 3
                ),
                "last_error_code": row.last_error_code,
                "correlation_id": row.correlation_id,
                "created_at": row.created_at,
                "completed_at": row.completed_at,
            }
            for row in rows
        ],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/connections/{connection_id}/deliveries/{delivery_id}/retry",
    response_model=IntegrationDeliveryRetryOut,
)
async def retry_failed_delivery(
    connection_id: UUID,
    delivery_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> IntegrationDeliveryRetryOut:
    """Requeue one terminal failed delivery without changing its idempotency key."""
    connection = await _require_connection(db, user.organization_id, connection_id)
    if connection.status != "connected":
        raise HTTPException(status_code=409, detail="A connected integration is required")

    job = await db.scalar(
        select(IntegrationDeliveryJob)
        .where(
            IntegrationDeliveryJob.organization_id == user.organization_id,
            IntegrationDeliveryJob.connection_id == connection_id,
            IntegrationDeliveryJob.id == delivery_id,
        )
        .with_for_update()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Delivery job not found")
    if job.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed deliveries can be retried")
    if job.manual_retry_count >= 3:
        raise HTTPException(status_code=409, detail="Manual retry limit reached for this delivery")

    job.manual_retry_count += 1
    job.attempt_count = 0
    job.status = "queued"
    job.next_attempt_at = datetime.now(UTC)
    job.lease_expires_at = None
    job.completed_at = None
    job.last_error_code = None
    logger.info(
        "integration_delivery_manual_retry_queued",
        extra={
            "organization_id": str(user.organization_id),
            "connection_id": str(connection_id),
            "delivery_id": str(job.id),
            "message_id": str(job.message_id),
            "actor_user_id": str(user.id),
            "manual_retry_count": job.manual_retry_count,
        },
    )
    return IntegrationDeliveryRetryOut(
        id=job.id,
        status="queued",
        manual_retry_count=job.manual_retry_count,
        message="Outbound delivery queued for another attempt.",
    )


@router.post(
    "/connections/{connection_id}/disconnect",
    response_model=IntegrationConnectionEventOut,
)
async def disconnect_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> IntegrationConnectionEventOut:
    connection = await db.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.organization_id == user.organization_id,
        )
        .with_for_update()
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    await disconnect_generic_connection(db, connection)
    configuration = connection.safe_configuration if isinstance(connection.safe_configuration, dict) else {}
    record_connection_audit(
        db,
        connection,
        event_type="disconnected",
        actor_user_id=user.id,
        auth_mode=configuration.get("auth_mode") if isinstance(configuration.get("auth_mode"), str) else None,
        granted_scopes=configuration.get("granted_scopes") if isinstance(configuration.get("granted_scopes"), list) else None,
    )
    return IntegrationConnectionEventOut(
        status="disconnected",
        message=f"{connection.display_name} was disconnected and its stored credentials were removed.",
    )


async def _require_connection(
    db: AsyncSession, organization_id: UUID, connection_id: UUID
) -> IntegrationConnection:
    connection = await db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.organization_id == organization_id,
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return connection


def _validate_pagination(limit: int, offset: int) -> None:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Invalid pagination parameters")
