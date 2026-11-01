import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db, set_tenant_context
from app.integrations.providers.shopify.client import effective_shopify_scopes
from app.integrations.providers.shopify.security import normalize_shop_domain, verify_webhook_hmac
from app.models import (
    CatalogProduct,
    CatalogSyncJob,
    CatalogWebhookEvent,
    IntegrationConnection,
    ShopifyInstallation,
    User,
)
from app.schemas.catalog import (
    CatalogProductOut,
    CatalogProductPageOut,
    CatalogStatusOut,
    CatalogSyncJobOut,
    CatalogSyncRequest,
    CatalogWebhookAccepted,
)
from app.services.catalog import MAX_SYNC_ATTEMPTS, connected_shopify_connection

router = APIRouter(tags=["commerce catalog"])
webhook_router = APIRouter(prefix="/integrations/shopify/webhooks", tags=["Shopify webhooks"])
MAX_WEBHOOK_BYTES = 256 * 1024
SUPPORTED_PRODUCT_TOPICS = {"products/create", "products/update", "products/delete"}


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
        latest = await db.scalar(
            select(CatalogSyncJob)
            .where(
                CatalogSyncJob.organization_id == user.organization_id,
                CatalogSyncJob.connection_id == connection.id,
            )
            .order_by(CatalogSyncJob.created_at.desc())
            .limit(1)
        )
        if latest:
            last_sync = latest.completed_at if latest.status == "succeeded" else None
            last_error = latest.last_error_code
    granted = set(installation.granted_scopes or []) if installation else set()
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
    if "read_products" not in effective_shopify_scopes(installation.granted_scopes):
        raise HTTPException(status_code=403, detail="Shopify read_products permission is required; reconnect and grant product access")
    running = await db.scalar(
        select(CatalogSyncJob).where(
            CatalogSyncJob.organization_id == user.organization_id,
            CatalogSyncJob.connection_id == connection.id,
            CatalogSyncJob.status.in_(("queued", "running")),
        ).order_by(CatalogSyncJob.created_at.desc()).limit(1)
    )
    if running:
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
        attempt_count=0,
        max_attempts=MAX_SYNC_ATTEMPTS,
        next_attempt_at=now,
        updated_after=watermark,
    )
    db.add(job)
    await db.flush()
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
    supplied = request.headers.get("x-shopify-hmac-sha256", "")
    if not verify_webhook_hmac(raw, supplied):
        raise HTTPException(status_code=401, detail="Invalid Shopify webhook signature")
    topic = request.headers.get("x-shopify-topic", "").lower()
    event_key = request.headers.get("x-shopify-webhook-id", "")[:512]
    shop_header = request.headers.get("x-shopify-shop-domain", "")
    if topic not in SUPPORTED_PRODUCT_TOPICS or not event_key:
        raise HTTPException(status_code=400, detail="Unsupported or incomplete Shopify product webhook")
    try:
        shop_domain = normalize_shop_domain(shop_header)
        payload = json.loads(raw)
        external_id = str(payload["id"])
        if not external_id.isdigit():
            raise ValueError("invalid_product_id")
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid Shopify product webhook payload") from None
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
    existing = await db.scalar(
        select(CatalogWebhookEvent).where(
            CatalogWebhookEvent.organization_id == organization_id,
            CatalogWebhookEvent.connection_id == connection_id,
            CatalogWebhookEvent.provider_id == "shopify",
            CatalogWebhookEvent.external_event_id == event_key,
        )
    )
    if existing:
        return CatalogWebhookAccepted(duplicate=True)
    from app.integrations.providers.shopify.catalog import _gid

    event = CatalogWebhookEvent(
        organization_id=organization_id,
        connection_id=connection_id,
        provider_id="shopify",
        external_event_id=event_key,
        event_type=topic,
        external_product_id=_gid(external_id, "Product"),
        payload={},
        status="queued",
        attempt_count=0,
        max_attempts=MAX_SYNC_ATTEMPTS,
        next_attempt_at=datetime.now(UTC),
    )
    db.add(event)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        await set_tenant_context(db, organization_id)
        return CatalogWebhookAccepted(duplicate=True)
    return CatalogWebhookAccepted()
