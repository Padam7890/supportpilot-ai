"""Tenant-scoped catalog persistence and durable provider sync operations."""

import random
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, set_tenant_context
from app.integrations.core.contracts.catalog import CatalogProductSnapshot
from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.providers.shopify.catalog import ShopifyProductCatalogAdapter
from app.integrations.providers.shopify.client import ShopifyAPIError, effective_shopify_scopes
from app.models import (
    CatalogProduct,
    CatalogSyncJob,
    CatalogVariant,
    CatalogWebhookEvent,
    IntegrationConnection,
    ShopifyInstallation,
)
from app.services.integration_connections import sync_shopify_connection

PAGE_SIZE = 20
MAX_SYNC_ATTEMPTS = 5
JOB_LEASE = timedelta(minutes=5)


async def resolve_shopify_credentials(connection_ref: IntegrationConnectionRef) -> tuple[str, str]:
    """Resolve a tenant connection's active token for provider calls."""
    async with SessionLocal() as db:
        await set_tenant_context(db, connection_ref.organization_id)
        installation = await db.scalar(
            select(ShopifyInstallation).where(
                ShopifyInstallation.organization_id == connection_ref.organization_id,
                ShopifyInstallation.disconnected_at.is_(None),
            )
        )
        if installation is None or installation.shop_domain != connection_ref.external_account_id:
            raise LookupError("catalog_not_connected")
        from app.api.routes.integrations import valid_access_token
        try:
            token = await valid_access_token(db, installation)
        except HTTPException as exc:
            code = (
                "shopify_scope_or_data_access_required"
                if exc.status_code == 403
                else "shopify_reauthorization_required"
                if exc.status_code == 409
                else "shopify_unavailable"
            )
            raise ShopifyAPIError(code, status_code=exc.status_code) from exc
        await db.commit()
        return installation.shop_domain, token


async def connected_shopify_connection(
    db: AsyncSession, organization_id: uuid.UUID
) -> tuple[ShopifyInstallation, IntegrationConnection]:
    installation = await db.scalar(
        select(ShopifyInstallation).where(
            ShopifyInstallation.organization_id == organization_id,
            ShopifyInstallation.disconnected_at.is_(None),
        )
    )
    if installation is None or not installation.access_token_encrypted:
        raise LookupError("catalog_not_connected")
    connection = await sync_shopify_connection(db, installation)
    if connection.status != "connected":
        raise LookupError("catalog_not_connected")
    return installation, connection


def connection_ref(connection: IntegrationConnection) -> IntegrationConnectionRef:
    return IntegrationConnectionRef(
        id=connection.id,
        organization_id=connection.organization_id,
        provider_id=connection.provider_id,
        external_account_id=connection.external_account_id,
    )


async def upsert_product_snapshot(
    db: AsyncSession,
    *,
    organization_id: uuid.UUID,
    connection_id: uuid.UUID,
    snapshot: CatalogProductSnapshot,
    sync_id: uuid.UUID | None = None,
) -> CatalogProduct:
    now = datetime.now(UTC)
    product = await db.scalar(
        select(CatalogProduct)
        .where(
            CatalogProduct.organization_id == organization_id,
            CatalogProduct.connection_id == connection_id,
            CatalogProduct.external_product_id == snapshot.external_product_id,
        )
        .with_for_update()
    )
    if product is None:
        product = CatalogProduct(
            organization_id=organization_id,
            connection_id=connection_id,
            external_product_id=snapshot.external_product_id,
            title=snapshot.title,
            synced_at=now,
        )
        db.add(product)
        await db.flush()
    product.title = snapshot.title
    product.description = snapshot.description
    product.brand = snapshot.brand
    product.category = snapshot.category
    product.images = [image.model_dump(mode="json") for image in snapshot.images]
    product.canonical_url = str(snapshot.canonical_url) if snapshot.canonical_url else None
    product.status = snapshot.status
    product.specifications = snapshot.specifications
    product.provider_updated_at = snapshot.provider_updated_at
    product.synced_at = now
    product.last_seen_sync_id = sync_id or product.last_seen_sync_id
    product.deleted_at = None

    incoming_ids: set[str] = set()
    for item in snapshot.variants:
        incoming_ids.add(item.external_variant_id)
        variant = await db.scalar(
            select(CatalogVariant)
            .where(
                CatalogVariant.organization_id == organization_id,
                CatalogVariant.connection_id == connection_id,
                CatalogVariant.external_variant_id == item.external_variant_id,
            )
            .with_for_update()
        )
        if variant is None:
            variant = CatalogVariant(
                organization_id=organization_id,
                connection_id=connection_id,
                product_id=product.id,
                external_variant_id=item.external_variant_id,
                title=item.title,
                price=Decimal(item.price),
                currency=item.currency,
                synced_at=now,
            )
            db.add(variant)
        variant.product_id = product.id
        variant.title = item.title
        variant.sku = item.sku
        variant.attributes = item.attributes
        variant.price = Decimal(item.price)
        variant.compare_at_price = Decimal(item.compare_at_price) if item.compare_at_price is not None else None
        variant.currency = item.currency
        variant.availability = item.availability
        variant.provider_updated_at = item.provider_updated_at
        variant.synced_at = now
        variant.deleted_at = None
    existing_variants = (
        await db.scalars(
            select(CatalogVariant).where(
                CatalogVariant.organization_id == organization_id,
                CatalogVariant.connection_id == connection_id,
                CatalogVariant.product_id == product.id,
                CatalogVariant.deleted_at.is_(None),
            )
        )
    ).all()
    for existing in existing_variants:
        if existing.external_variant_id not in incoming_ids:
            existing.deleted_at = now
    await db.flush()
    return product


async def run_catalog_sync_page(
    organization_id: uuid.UUID,
    job_id: uuid.UUID,
    *,
    resolve_credentials,
) -> bool:
    """Process one bounded page and persist its cursor before returning."""
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        job = await db.scalar(
            select(CatalogSyncJob)
            .where(CatalogSyncJob.organization_id == organization_id, CatalogSyncJob.id == job_id)
            .with_for_update(skip_locked=True)
        )
        if job is None or job.status != "running":
            await db.rollback()
            return False
        connection = await db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.organization_id == organization_id,
                IntegrationConnection.id == job.connection_id,
                IntegrationConnection.provider_id == "shopify",
                IntegrationConnection.status == "connected",
            )
        )
        installation = await db.scalar(
            select(ShopifyInstallation).where(
                ShopifyInstallation.organization_id == organization_id,
                ShopifyInstallation.disconnected_at.is_(None),
            )
        )
        if (
            connection is None
            or installation is None
            or connection.external_account_id != installation.shop_domain
        ):
            job.status = "failed"
            job.last_error_code = "catalog_not_connected"
            job.completed_at = now
            await db.commit()
            return True
        scopes = set(installation.granted_scopes or [])
        if "read_products" not in effective_shopify_scopes(scopes):
            job.status = "failed"
            job.last_error_code = "product_scope_missing"
            job.completed_at = now
            await db.commit()
            return True
        ref = connection_ref(connection)
        cursor, mode, updated_after = job.cursor, job.mode, job.updated_after
        if job.sync_started_at is None:
            job.sync_started_at = now
            job.started_at = now
        await db.commit()

    adapter = ShopifyProductCatalogAdapter(resolve_credentials)
    try:
        page = await adapter.list_products(
            ref,
            limit=PAGE_SIZE,
            cursor=cursor,
            updated_after=updated_after if mode == "incremental" else None,
        )
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            job = await db.scalar(
                select(CatalogSyncJob)
                .where(CatalogSyncJob.organization_id == organization_id, CatalogSyncJob.id == job_id)
                .with_for_update()
            )
            if job is None or job.status != "running":
                await db.rollback()
                return False
            for snapshot in page.items:
                await upsert_product_snapshot(
                    db,
                    organization_id=organization_id,
                    connection_id=job.connection_id,
                    snapshot=snapshot,
                    sync_id=job.id if mode in {"full", "reconcile"} else None,
                )
            job.records_seen += len(page.items)
            job.attempt_count = 0
            job.cursor = page.next_cursor
            if not page.has_more:
                if mode in {"full", "reconcile"}:
                    await db.execute(
                        CatalogProduct.__table__.update()
                        .where(
                            CatalogProduct.organization_id == organization_id,
                            CatalogProduct.connection_id == job.connection_id,
                            CatalogProduct.deleted_at.is_(None),
                            or_(CatalogProduct.last_seen_sync_id.is_(None), CatalogProduct.last_seen_sync_id != job.id),
                            CatalogProduct.synced_at <= job.sync_started_at,
                        )
                        .values(deleted_at=now)
                    )
                job.status = "succeeded"
                job.completed_at = now
            else:
                job.status = "queued"
                job.next_attempt_at = now
            job.lease_expires_at = None
            await db.commit()
        return True
    except (ShopifyAPIError, TimeoutError, OSError) as exc:
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            job = await db.scalar(
                select(CatalogSyncJob)
                .where(CatalogSyncJob.organization_id == organization_id, CatalogSyncJob.id == job_id)
                .with_for_update()
            )
            if job is None:
                await db.rollback()
                return False
            job.last_error_code = exc.code if isinstance(exc, ShopifyAPIError) else "provider_unavailable"
            job.lease_expires_at = None
            retryable = not isinstance(exc, ShopifyAPIError) or exc.status_code == 429 or exc.status_code >= 500
            if retryable:
                job.attempt_count += 1
            if not retryable or job.attempt_count >= job.max_attempts:
                job.status = "failed"
                job.completed_at = datetime.now(UTC)
            else:
                delay = min(30 * (2 ** max(job.attempt_count - 1, 0)), 1800)
                job.status = "queued"
                job.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay + random.uniform(0, delay * 0.2))
            await db.commit()
        return True


async def claim_catalog_job(organization_id: uuid.UUID) -> uuid.UUID | None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        job = await db.scalar(
            select(CatalogSyncJob)
            .where(
                CatalogSyncJob.organization_id == organization_id,
                CatalogSyncJob.attempt_count < CatalogSyncJob.max_attempts,
                or_(
                    and_(CatalogSyncJob.status == "queued", CatalogSyncJob.next_attempt_at <= now),
                    and_(CatalogSyncJob.status == "running", CatalogSyncJob.lease_expires_at < now),
                ),
            )
            .order_by(CatalogSyncJob.created_at, CatalogSyncJob.id)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            await db.rollback()
            return None
        if job.status == "running":
            job.attempt_count += 1
            if job.attempt_count >= job.max_attempts:
                job.status = "failed"
                job.completed_at = now
                job.last_error_code = "worker_lease_expired"
                await db.commit()
                return None
        job.status = "running"
        job.lease_expires_at = now + JOB_LEASE
        await db.commit()
        return job.id


async def claim_catalog_webhook(organization_id: uuid.UUID) -> uuid.UUID | None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        event = await db.scalar(
            select(CatalogWebhookEvent)
            .where(
                CatalogWebhookEvent.organization_id == organization_id,
                or_(
                    and_(CatalogWebhookEvent.status == "queued", CatalogWebhookEvent.next_attempt_at <= now),
                    and_(CatalogWebhookEvent.status == "running", CatalogWebhookEvent.updated_at < now - JOB_LEASE),
                ),
            )
            .order_by(CatalogWebhookEvent.created_at, CatalogWebhookEvent.id)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            await db.rollback()
            return None
        if event.status == "running":
            event.attempt_count += 1
        if event.attempt_count >= event.max_attempts:
            event.status = "failed"
            event.completed_at = now
            event.last_error_code = "worker_lease_expired"
            await db.commit()
            return None
        event.status = "running"
        await db.commit()
        return event.id


async def process_catalog_webhook(
    organization_id: uuid.UUID,
    event_id: uuid.UUID,
    *,
    resolve_credentials,
) -> bool:
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        event = await db.scalar(
            select(CatalogWebhookEvent)
            .where(CatalogWebhookEvent.organization_id == organization_id, CatalogWebhookEvent.id == event_id)
            .with_for_update()
        )
        if event is None or event.status not in {"queued", "running"}:
            await db.rollback()
            return False
        event.status = "running"
        connection = await db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.organization_id == organization_id,
                IntegrationConnection.id == event.connection_id,
                IntegrationConnection.status == "connected",
            )
        )
        installation = await db.scalar(
            select(ShopifyInstallation).where(
                ShopifyInstallation.organization_id == organization_id,
                ShopifyInstallation.disconnected_at.is_(None),
            )
        )
        if (
            connection is None
            or installation is None
            or connection.external_account_id != installation.shop_domain
            or "read_products" not in effective_shopify_scopes(installation.granted_scopes or [])
        ):
            event.status = "failed"
            event.last_error_code = "product_scope_missing"
            event.completed_at = datetime.now(UTC)
            await db.commit()
            return True
        ref = connection_ref(connection)
        conn_id = connection.id
        topic, product_gid = event.event_type, event.external_product_id
        await db.commit()
    try:
        if topic == "products/delete":
            async with SessionLocal() as db:
                await set_tenant_context(db, organization_id)
                now = datetime.now(UTC)
                product = await db.scalar(
                    select(CatalogProduct).where(
                        CatalogProduct.organization_id == organization_id,
                        CatalogProduct.connection_id == conn_id,
                        CatalogProduct.external_product_id == product_gid,
                    ).with_for_update()
                )
                if product:
                    product.deleted_at = now
                    await db.execute(
                        CatalogVariant.__table__.update()
                        .where(CatalogVariant.organization_id == organization_id, CatalogVariant.product_id == product.id)
                        .values(deleted_at=now)
                    )
                event = await db.scalar(select(CatalogWebhookEvent).where(CatalogWebhookEvent.organization_id == organization_id, CatalogWebhookEvent.id == event_id).with_for_update())
                if event:
                    event.status = "succeeded"
                    event.completed_at = now
                await db.commit()
            return True
        snapshot = await ShopifyProductCatalogAdapter(resolve_credentials).get_product(ref, external_product_id=product_gid)
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            if snapshot is None:
                existing = await db.scalar(select(CatalogProduct).where(CatalogProduct.organization_id == organization_id, CatalogProduct.connection_id == conn_id, CatalogProduct.external_product_id == product_gid).with_for_update())
                if existing:
                    existing.deleted_at = datetime.now(UTC)
            else:
                await upsert_product_snapshot(db, organization_id=organization_id, connection_id=conn_id, snapshot=snapshot)
            event = await db.scalar(select(CatalogWebhookEvent).where(CatalogWebhookEvent.organization_id == organization_id, CatalogWebhookEvent.id == event_id).with_for_update())
            if event:
                event.status = "succeeded"
                event.completed_at = datetime.now(UTC)
            await db.commit()
        return True
    except (ShopifyAPIError, TimeoutError, OSError) as exc:
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            event = await db.scalar(select(CatalogWebhookEvent).where(CatalogWebhookEvent.organization_id == organization_id, CatalogWebhookEvent.id == event_id).with_for_update())
            if event:
                event.last_error_code = exc.code if isinstance(exc, ShopifyAPIError) else "provider_unavailable"
                retryable = not isinstance(exc, ShopifyAPIError) or exc.status_code == 429 or exc.status_code >= 500
                if retryable:
                    event.attempt_count += 1
                if not retryable or event.attempt_count >= event.max_attempts:
                    event.status = "failed"
                    event.completed_at = datetime.now(UTC)
                else:
                    event.status = "queued"
                    delay = min(30 * 2 ** (event.attempt_count - 1), 1800)
                    event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay + random.uniform(0, delay * 0.2))
                await db.commit()
        return True


async def enqueue_reconciliation(organization_id: uuid.UUID) -> bool:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        connection = await db.scalar(
            select(IntegrationConnection)
            .where(
                IntegrationConnection.organization_id == organization_id,
                IntegrationConnection.provider_id == "shopify",
                IntegrationConnection.status == "connected",
            )
            .with_for_update(skip_locked=True)
        )
        if connection is None:
            await db.rollback()
            return False
        installation = await db.scalar(
            select(ShopifyInstallation).where(
                ShopifyInstallation.organization_id == organization_id,
                ShopifyInstallation.disconnected_at.is_(None),
            )
        )
        if (
            installation is None
            or installation.shop_domain != connection.external_account_id
            or "read_products" not in effective_shopify_scopes(installation.granted_scopes or [])
        ):
            await db.rollback()
            return False
        recent = await db.scalar(
            select(func.count(CatalogSyncJob.id)).where(
                CatalogSyncJob.organization_id == organization_id,
                CatalogSyncJob.connection_id == connection.id,
                CatalogSyncJob.mode == "reconcile",
                CatalogSyncJob.created_at > now - timedelta(hours=24),
                CatalogSyncJob.status.in_(("queued", "running", "succeeded", "failed")),
            )
        )
        if recent:
            await db.rollback()
            return False
        db.add(CatalogSyncJob(
            organization_id=organization_id,
            connection_id=connection.id,
            mode="reconcile",
            status="queued",
            attempt_count=0,
            max_attempts=MAX_SYNC_ATTEMPTS,
            next_attempt_at=now,
            updated_after=None,
        ))
        await db.commit()
        return True
