import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_roles
from app.core.observability import current_correlation_id
from app.db.session import get_db, set_tenant_context
from app.integrations.core import (
    IntegrationCapability,
    IntegrationError,
    IntegrationErrorCode,
    WebhookCapability,
)
from app.integrations.providers.shopify.client import (
    effective_shopify_scopes,
    log_shopify_api_event,
    log_shopify_event,
)
from app.models import (
    CatalogProduct,
    CatalogSyncJob,
    CatalogWebhookEvent,
    IntegrationConnection,
    IntegrationWebhookEvent,
    ShopifyInstallation,
    User,
)
from app.schemas.catalog import (
    CatalogProductOut,
    CatalogProductPageOut,
    CatalogStatusOut,
    CatalogSyncJobOut,
    CatalogSyncJobPageOut,
    CatalogSyncRequest,
    CatalogWebhookAccepted,
)
from app.services.catalog import MAX_SYNC_ATTEMPTS, connected_shopify_connection

router = APIRouter(tags=["commerce catalog"])
webhook_router = APIRouter(prefix="/integrations/shopify/webhooks", tags=["Shopify webhooks"])
MAX_WEBHOOK_BYTES = 256 * 1024
MAX_MANUAL_CATALOG_RETRIES = 3


@router.get("/catalog/status", response_model=CatalogStatusOut)
async def catalog_status(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> CatalogStatusOut:
    installation = await db.scalar(
        select(ShopifyInstallation).where(ShopifyInstallation.organization_id == user.organization_id)
    )
    connection = await db.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.organization_id == user.organization_id,
            IntegrationConnection.provider_id == "shopify",
            IntegrationConnection.status == "connected",
        )
        .order_by(IntegrationConnection.updated_at.desc())
    )
    if installation is not None and connection is not None and connection.external_account_id != installation.shop_domain:
        connection = None
    count = 0
    last_sync = None
    last_error = None
    if connection:
        count = await db.scalar(
            select(func.count(CatalogProduct.id)).where(
                CatalogProduct.organization_id == user.organization_id,
                CatalogProduct.connection_id == connection.id,
                CatalogProduct.deleted_at.is_(None),
            )
        ) or 0
        latest_completed_sync = await db.scalar(
            select(CatalogSyncJob)
            .where(
                CatalogSyncJob.organization_id == user.organization_id,
                CatalogSyncJob.connection_id == connection.id,
                CatalogSyncJob.status.in_(("succeeded", "failed")),
                CatalogSyncJob.completed_at.is_not(None),
            )
            .order_by(CatalogSyncJob.completed_at.desc(), CatalogSyncJob.id.desc())
            .limit(1)
        )
        last_success = await db.scalar(
            select(CatalogSyncJob)
            .where(
                CatalogSyncJob.organization_id == user.organization_id,
                CatalogSyncJob.connection_id == connection.id,
                CatalogSyncJob.status == "succeeded",
                CatalogSyncJob.completed_at.is_not(None),
            )
            .order_by(CatalogSyncJob.completed_at.desc(), CatalogSyncJob.id.desc())
            .limit(1)
        )
        # A later successful completion supersedes an older failed attempt, even
        # when overlapping jobs were created in a different order than they ran.
        if latest_completed_sync and latest_completed_sync.status == "failed":
            last_error = latest_completed_sync.last_error_code
        if last_success:
            last_sync = last_success.completed_at
    granted = set(installation.granted_scopes or []) if installation else set()
    effective = effective_shopify_scopes(granted)
    missing_catalog_scopes = {"read_products"} - effective
    log_shopify_event(
        "scope_check",
        source="catalog_status",
        organization_id=str(user.organization_id),
        shop_domain=installation.shop_domain if installation else None,
        granted_scopes=sorted(granted),
        effective_scopes=sorted(effective),
        required_catalog_scopes=["read_products"],
        missing_catalog_scopes=sorted(missing_catalog_scopes),
        product_count=count,
        latest_sync_error_code=last_error,
    )
    return CatalogStatusOut(
        connected=bool(connection and installation and installation.disconnected_at is None),
        product_scope_granted="read_products" in effective_shopify_scopes(granted),
        product_count=count,
        last_sync_at=last_sync,
        last_error_code=last_error,
    )


@router.get("/catalog/products", response_model=CatalogProductPageOut)
async def list_catalog_products(
    query: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CatalogProductPageOut:
    installation = await db.scalar(
        select(ShopifyInstallation).where(
            ShopifyInstallation.organization_id == user.organization_id,
            ShopifyInstallation.disconnected_at.is_(None),
        )
    )
    connection = await db.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.organization_id == user.organization_id,
            IntegrationConnection.provider_id == "shopify",
            IntegrationConnection.status == "connected",
        )
        .order_by(IntegrationConnection.updated_at.desc())
    )
    if connection is None or installation is None or connection.external_account_id != installation.shop_domain:
        raise HTTPException(status_code=409, detail="Connect Shopify before browsing the catalog")
    statement = select(CatalogProduct).where(
        CatalogProduct.organization_id == user.organization_id,
        CatalogProduct.connection_id == connection.id,
        CatalogProduct.deleted_at.is_(None),
    )
    if query and query.strip():
        needle = f"%{query.strip()[:120]}%"
        statement = statement.where(
            or_(CatalogProduct.title.ilike(needle), CatalogProduct.description.ilike(needle), CatalogProduct.brand.ilike(needle))
        )
    total = await db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = (
        await db.scalars(
            statement.options(selectinload(CatalogProduct.variants))
            .order_by(CatalogProduct.title, CatalogProduct.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    for product in rows:
        product.variants = [variant for variant in product.variants if variant.deleted_at is None]
    return CatalogProductPageOut(items=[CatalogProductOut.model_validate(row) for row in rows], total=total, limit=limit, offset=offset)


@router.get("/catalog/products/{product_id}", response_model=CatalogProductOut)
async def get_catalog_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CatalogProductOut:
    product = await db.scalar(
        select(CatalogProduct)
        .where(
            CatalogProduct.organization_id == user.organization_id,
            CatalogProduct.id == product_id,
            CatalogProduct.deleted_at.is_(None),
        )
        .options(selectinload(CatalogProduct.variants))
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Catalog product not found")
    product.variants = [variant for variant in product.variants if variant.deleted_at is None]
    return CatalogProductOut.model_validate(product)


@router.post("/catalog/sync", response_model=CatalogSyncJobOut, status_code=status.HTTP_202_ACCEPTED)
async def start_catalog_sync(
    payload: CatalogSyncRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> CatalogSyncJobOut:
    installation, connection = await connected_shopify_connection(db, user.organization_id)
    await db.scalar(
        select(IntegrationConnection.id)
        .where(
            IntegrationConnection.organization_id == user.organization_id,
            IntegrationConnection.id == connection.id,
        )
        .with_for_update()
    )
    granted = set(installation.granted_scopes or [])
    effective = effective_shopify_scopes(granted)
    missing = {"read_products"} - effective
    log_shopify_event(
        "scope_check",
        source="catalog_sync_request",
        organization_id=str(user.organization_id),
        shop_domain=installation.shop_domain,
        granted_scopes=sorted(granted),
        effective_scopes=sorted(effective),
        required_catalog_scopes=["read_products"],
        missing_catalog_scopes=sorted(missing),
    )
    if missing:
        raise HTTPException(status_code=403, detail="Shopify read_products permission is required; reconnect and grant product access")
    running = await db.scalar(
        select(CatalogSyncJob).where(
            CatalogSyncJob.organization_id == user.organization_id,
            CatalogSyncJob.connection_id == connection.id,
            CatalogSyncJob.status.in_(("queued", "running")),
        ).order_by(CatalogSyncJob.created_at.desc()).limit(1)
    )
    if running:
        log_shopify_api_event(
            "catalog_sync_job_reused",
            organization_id=str(user.organization_id),
            connection_id=str(connection.id),
            job_id=str(running.id),
            job_status=running.status,
            mode=running.mode,
        )
        return CatalogSyncJobOut.model_validate(running)
    now = datetime.now(UTC)
    mode = payload.mode
    watermark = None
    if mode == "incremental":
        previous = await db.scalar(
            select(CatalogSyncJob)
            .where(
                CatalogSyncJob.organization_id == user.organization_id,
                CatalogSyncJob.connection_id == connection.id,
                CatalogSyncJob.status == "succeeded",
            )
            .order_by(CatalogSyncJob.completed_at.desc())
            .limit(1)
        )
        if previous is None:
            mode = "full"
        elif previous.completed_at is not None:
            watermark = previous.completed_at - timedelta(minutes=5)
    job = CatalogSyncJob(
        organization_id=user.organization_id,
        connection_id=connection.id,
        mode=mode,
        status="queued",
        correlation_id=current_correlation_id(),
        attempt_count=0,
        max_attempts=MAX_SYNC_ATTEMPTS,
        next_attempt_at=now,
        updated_after=watermark,
    )
    db.add(job)
    await db.flush()
    log_shopify_api_event(
        "catalog_sync_job_queued",
        organization_id=str(user.organization_id),
        connection_id=str(connection.id),
        job_id=str(job.id),
        job_status=job.status,
        mode=job.mode,
    )
    return CatalogSyncJobOut.model_validate(job)


@router.get("/catalog/sync-jobs/{job_id}", response_model=CatalogSyncJobOut)
async def get_catalog_sync_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CatalogSyncJobOut:
    job = await db.scalar(select(CatalogSyncJob).where(CatalogSyncJob.organization_id == user.organization_id, CatalogSyncJob.id == job_id))
    if job is None:
        raise HTTPException(status_code=404, detail="Catalog sync job not found")
    return CatalogSyncJobOut.model_validate(job)


@router.post(
    "/catalog/sync-jobs/{job_id}/retry",
    response_model=CatalogSyncJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_catalog_sync_job(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> CatalogSyncJobOut:
    """Requeue a failed tenant catalog sync from its first page."""
    installation, connection = await connected_shopify_connection(db, user.organization_id)
    await db.scalar(
        select(IntegrationConnection.id)
        .where(
            IntegrationConnection.organization_id == user.organization_id,
            IntegrationConnection.id == connection.id,
        )
        .with_for_update()
    )
    if "read_products" not in effective_shopify_scopes(set(installation.granted_scopes or [])):
        raise HTTPException(status_code=403, detail="Shopify product access is not available")

    job = await db.scalar(
        select(CatalogSyncJob)
        .where(
            CatalogSyncJob.organization_id == user.organization_id,
            CatalogSyncJob.connection_id == connection.id,
            CatalogSyncJob.id == job_id,
        )
        .with_for_update()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="Catalog sync job not found")
    if job.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed catalog syncs can be retried")
    if job.manual_retry_count >= MAX_MANUAL_CATALOG_RETRIES:
        raise HTTPException(status_code=409, detail="This catalog sync has reached its manual retry limit")

    active_job = await db.scalar(
        select(CatalogSyncJob.id)
        .where(
            CatalogSyncJob.organization_id == user.organization_id,
            CatalogSyncJob.connection_id == connection.id,
            CatalogSyncJob.id != job.id,
            CatalogSyncJob.status.in_(("queued", "running")),
        )
        .with_for_update()
    )
    if active_job is not None:
        raise HTTPException(status_code=409, detail="Another catalog sync is already in progress")

    now = datetime.now(UTC)
    job.status = "queued"
    job.attempt_count = 0
    job.manual_retry_count += 1
    job.last_manual_retry_by_user_id = user.id
    job.last_manual_retry_at = now
    job.next_attempt_at = now
    job.cursor = None
    job.sync_started_at = None
    job.started_at = None
    job.completed_at = None
    job.lease_expires_at = None
    job.records_seen = 0
    job.last_error_code = None
    job.correlation_id = current_correlation_id()
    await db.flush()
    log_shopify_api_event(
        "catalog_sync_manually_requeued",
        organization_id=str(user.organization_id),
        connection_id=str(connection.id),
        job_id=str(job.id),
        actor_user_id=str(user.id),
        manual_retry_count=job.manual_retry_count,
        job_status=job.status,
        mode=job.mode,
    )
    return CatalogSyncJobOut.model_validate(job)


@router.get("/catalog/sync-jobs", response_model=CatalogSyncJobPageOut)
async def list_catalog_sync_jobs(
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0, le=100000),
    connection_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CatalogSyncJobPageOut:
    filters = [CatalogSyncJob.organization_id == user.organization_id]
    if connection_id is not None:
        connection_exists = await db.scalar(
            select(IntegrationConnection.id).where(
                IntegrationConnection.id == connection_id,
                IntegrationConnection.organization_id == user.organization_id,
                IntegrationConnection.provider_id == "shopify",
            )
        )
        if connection_exists is None:
            raise HTTPException(status_code=404, detail="Shopify connection not found")
        filters.append(CatalogSyncJob.connection_id == connection_id)
    total = await db.scalar(
        select(func.count()).select_from(CatalogSyncJob).where(*filters)
    ) or 0
    jobs = await db.scalars(
        select(CatalogSyncJob)
        .where(*filters)
        .order_by(CatalogSyncJob.created_at.desc(), CatalogSyncJob.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return CatalogSyncJobPageOut(
        items=[CatalogSyncJobOut.model_validate(job) for job in jobs],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@webhook_router.post("/catalog/{organization_id}/{connection_id}", response_model=CatalogWebhookAccepted)
async def shopify_catalog_webhook(
    organization_id: UUID,
    connection_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> CatalogWebhookAccepted:
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_WEBHOOK_BYTES:
            raise HTTPException(status_code=413, detail="Webhook payload exceeds the size limit")
        body.extend(chunk)
    raw = bytes(body)
    try:
        registry = request.app.state.integration_registry
        verifier = registry.get_capability(
            "shopify", IntegrationCapability.WEBHOOKS, WebhookCapability
        )
        normalized_event = verifier.verify_and_normalize(
            headers=dict(request.headers.items()), raw_body=raw
        )
    except IntegrationError as exc:
        if exc.code is IntegrationErrorCode.PERMISSION_DENIED:
            raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature") from None
        if exc.code is IntegrationErrorCode.INVALID_PAYLOAD:
            raise HTTPException(status_code=400, detail="Invalid Shopify product webhook payload") from None
        raise HTTPException(status_code=503, detail="Shopify webhook verification is unavailable") from None
    topic = normalized_event.event_type
    event_key = normalized_event.external_event_id
    shop_domain = normalized_event.external_account_id
    external_product_id = normalized_event.normalized_payload["external_product_id"]
    await set_tenant_context(db, organization_id)
    connection = await db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.organization_id == organization_id,
            IntegrationConnection.id == connection_id,
            IntegrationConnection.provider_id == "shopify",
            IntegrationConnection.status == "connected",
            IntegrationConnection.external_account_id == shop_domain,
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Shopify webhook connection not found")
    payload_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "event_type": topic,
                "external_account_id": shop_domain,
                "normalized_payload": normalized_event.normalized_payload,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    durable_event_id = await db.scalar(
        pg_insert(IntegrationWebhookEvent)
        .values(
            organization_id=organization_id,
            connection_id=connection_id,
            provider_id=normalized_event.provider_id,
            external_event_id=event_key,
            event_type=topic,
            occurred_at=normalized_event.occurred_at,
            payload_fingerprint=payload_fingerprint,
            normalized_payload=normalized_event.normalized_payload,
        )
        .on_conflict_do_nothing(constraint="uq_integration_webhook_events_dedupe")
        .returning(IntegrationWebhookEvent.id)
    )
    if durable_event_id is None:
        return CatalogWebhookAccepted(duplicate=True)
    queued_event_id = await db.scalar(
        pg_insert(CatalogWebhookEvent)
        .values(
            organization_id=organization_id,
            connection_id=connection_id,
            provider_id="shopify",
            external_event_id=event_key,
            event_type=topic,
            external_product_id=external_product_id,
            payload={},
            status="queued",
            attempt_count=0,
            max_attempts=MAX_SYNC_ATTEMPTS,
            next_attempt_at=datetime.now(UTC),
            occurred_at=normalized_event.occurred_at,
            correlation_id=current_correlation_id(),
        )
        .on_conflict_do_nothing(constraint="uq_catalog_webhook_events_dedupe")
        .returning(CatalogWebhookEvent.id)
    )
    if queued_event_id is None:
        await db.rollback()
        await set_tenant_context(db, organization_id)
        return CatalogWebhookAccepted(duplicate=True)
    await db.flush()
    return CatalogWebhookAccepted()
