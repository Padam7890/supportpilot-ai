"""Tenant-scoped catalog persistence and durable provider sync operations."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import SessionLocal, set_tenant_context
from app.integrations.core.contracts.catalog import CatalogProductSnapshot
from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.providers.shopify.catalog import ShopifyProductCatalogAdapter
from app.integrations.providers.shopify.client import (
    ShopifyAPIError,
    effective_shopify_scopes,
    log_shopify_api_event,
)
from app.models import (
    CatalogProduct,
    CatalogSyncJob,
    CatalogVariant,
    CatalogWebhookEvent,
    IntegrationConnection,
    ShopifyInstallation,
)
from app.services.integration_connections import sync_shopify_connection
from app.workers.domain.retry_policy import retry_delay_seconds

PAGE_SIZE = 20
MAX_SYNC_ATTEMPTS = 5
JOB_LEASE = timedelta(minutes=5)
logger = logging.getLogger(__name__)


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
            raise ShopifyAPIError("catalog_not_connected", status_code=409)
        from app.services.shopify_tokens import valid_access_token

        token_was_current = bool(
            installation.access_token_expires_at
            and installation.access_token_expires_at > datetime.now(UTC) + timedelta(minutes=5)
        )
        try:
            token = await valid_access_token(db, installation)
        except HTTPException as exc:
            code = (
                "shopify_required_scopes_missing"
                if exc.status_code == 403
                and "did not grant the required" in str(exc.detail).casefold()
                else "shopify_access_denied"
                if exc.status_code == 403
                else "shopify_reauthorization_required"
                if exc.status_code == 409
                else "shopify_credentials_unavailable"
                if exc.status_code == 503
                else "shopify_authorization_failed"
            )
            raise ShopifyAPIError(code, status_code=exc.status_code) from None
        effective_scopes = effective_shopify_scopes(installation.granted_scopes or [])
        log_shopify_api_event(
            "catalog_credentials_resolved",
            organization_id=str(connection_ref.organization_id),
            connection_id=str(connection_ref.id),
            shop_domain=installation.shop_domain,
            token_source="cached" if token_was_current else "refreshed",
            effective_scopes=sorted(effective_scopes),
            product_scope_granted="read_products" in effective_scopes,
        )
        if "read_products" not in effective_scopes:
            raise ShopifyAPIError("shopify_product_scope_missing", status_code=403)
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
        await db.execute(
            pg_insert(CatalogProduct)
            .values(
                id=uuid.uuid4(),
                organization_id=organization_id,
                connection_id=connection_id,
                external_product_id=snapshot.external_product_id,
                title=snapshot.title,
                status="unknown",
                images=[],
                specifications={},
                synced_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_catalog_products_external")
        )
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
            raise RuntimeError("Catalog product insert was not visible after conflict handling")
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
            await db.execute(
                pg_insert(CatalogVariant)
                .values(
                    id=uuid.uuid4(),
                    organization_id=organization_id,
                    connection_id=connection_id,
                    product_id=product.id,
                    external_variant_id=item.external_variant_id,
                    title=item.title,
                    price=Decimal(item.price),
                    currency=item.currency,
                    attributes={},
                    availability="unknown",
                    synced_at=now,
                )
                .on_conflict_do_nothing(constraint="uq_catalog_variants_external")
            )
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
                raise RuntimeError("Catalog variant insert was not visible after conflict handling")
        variant.product_id = product.id
        variant.title = item.title
        variant.sku = item.sku
        variant.attributes = item.attributes
        variant.price = Decimal(item.price)
        variant.compare_at_price = (
            Decimal(item.compare_at_price) if item.compare_at_price is not None else None
        )
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
        log_shopify_api_event(
            "catalog_sync_product_fetch_started",
            organization_id=str(organization_id),
            connection_id=str(ref.id),
            job_id=str(job_id),
            job_status="running",
            mode=mode,
            cursor_supplied=cursor is not None,
            request_attempted=False,
        )
        page = await adapter.list_products(
            ref,
            limit=PAGE_SIZE,
            cursor=cursor,
            updated_after=updated_after if mode == "incremental" else None,
            sync_job_id=job_id,
        )
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            job = await db.scalar(
                select(CatalogSyncJob)
                .where(
                    CatalogSyncJob.organization_id == organization_id, CatalogSyncJob.id == job_id
                )
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
            job.last_error_code = None
            if not page.has_more:
                if mode in {"full", "reconcile"}:
                    await db.execute(
                        CatalogProduct.__table__.update()
                        .where(
                            CatalogProduct.organization_id == organization_id,
                            CatalogProduct.connection_id == job.connection_id,
                            CatalogProduct.deleted_at.is_(None),
                            or_(
                                CatalogProduct.last_seen_sync_id.is_(None),
                                CatalogProduct.last_seen_sync_id != job.id,
                            ),
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
            persisted_product_count = len(page.items)
            persisted_variant_count = sum(len(product.variants) for product in page.items)
            final_status = job.status
            records_seen = job.records_seen
            await db.commit()
            log_shopify_api_event(
                "catalog_sync_page_succeeded",
                organization_id=str(organization_id),
                connection_id=str(ref.id),
                job_id=str(job_id),
                mode=mode,
                products_received=len(page.items),
                products_persisted=persisted_product_count,
                variants_persisted=persisted_variant_count,
                records_seen=records_seen,
                has_more=page.has_more,
                job_status=final_status,
                transaction_committed=True,
            )
        return True
    except (ShopifyAPIError, TimeoutError, OSError) as exc:
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            job = await db.scalar(
                select(CatalogSyncJob)
                .where(
                    CatalogSyncJob.organization_id == organization_id, CatalogSyncJob.id == job_id
                )
                .with_for_update()
            )
            if job is None:
                await db.rollback()
                return False
            job.last_error_code = (
                exc.code if isinstance(exc, ShopifyAPIError) else "provider_unavailable"
            )
            job.lease_expires_at = None
            retryable = (
                not isinstance(exc, ShopifyAPIError)
                or exc.status_code == 429
                or exc.status_code >= 500
            )
            if retryable:
                job.attempt_count += 1
            if not retryable or job.attempt_count >= job.max_attempts:
                job.status = "failed"
                job.completed_at = datetime.now(UTC)
            else:
                job.status = "queued"
                job.next_attempt_at = datetime.now(UTC) + timedelta(
                    seconds=retry_delay_seconds(
                        job.attempt_count, base_seconds=30, cap_seconds=1800
                    )
                )
            log_shopify_api_event(
                "catalog_sync_provider_failed",
                level=logging.ERROR,
                organization_id=str(organization_id),
                connection_id=str(job.connection_id),
                job_id=str(job.id),
                error_code=job.last_error_code,
                provider_reason_code=exc.reason_code if isinstance(exc, ShopifyAPIError) else None,
                provider_status_code=exc.status_code if isinstance(exc, ShopifyAPIError) else None,
                provider_diagnostics=list(exc.diagnostics)
                if isinstance(exc, ShopifyAPIError)
                else [],
                retryable=retryable,
                attempt_count=job.attempt_count,
                max_attempts=job.max_attempts,
                job_status=job.status,
            )
            await db.commit()
        return True
    except SQLAlchemyError as exc:
        log_shopify_api_event(
            "catalog_sync_persistence_failed",
            level=logging.ERROR,
            organization_id=str(organization_id),
            job_id=str(job_id),
            error_type=type(exc).__name__,
        )
        try:
            async with SessionLocal() as db:
                await set_tenant_context(db, organization_id)
                job = await db.scalar(
                    select(CatalogSyncJob)
                    .where(
                        CatalogSyncJob.organization_id == organization_id,
                        CatalogSyncJob.id == job_id,
                    )
                    .with_for_update()
                )
                if job is not None:
                    job.status = "failed"
                    job.last_error_code = "catalog_persistence_failed"
                    job.lease_expires_at = None
                    job.completed_at = datetime.now(UTC)
                    await db.commit()
        except SQLAlchemyError as status_error:
            log_shopify_api_event(
                "catalog_sync_failure_status_update_failed",
                level=logging.ERROR,
                organization_id=str(organization_id),
                job_id=str(job_id),
                error_type=type(status_error).__name__,
            )
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
                    and_(
                        CatalogWebhookEvent.status == "queued",
                        CatalogWebhookEvent.next_attempt_at <= now,
                    ),
                    and_(
                        CatalogWebhookEvent.status == "running",
                        CatalogWebhookEvent.updated_at < now - JOB_LEASE,
                    ),
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
            .where(
                CatalogWebhookEvent.organization_id == organization_id,
                CatalogWebhookEvent.id == event_id,
            )
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
                    select(CatalogProduct)
                    .where(
                        CatalogProduct.organization_id == organization_id,
                        CatalogProduct.connection_id == conn_id,
                        CatalogProduct.external_product_id == product_gid,
                    )
                    .with_for_update()
                )
                if product:
                    product.deleted_at = now
                    await db.execute(
                        CatalogVariant.__table__.update()
                        .where(
                            CatalogVariant.organization_id == organization_id,
                            CatalogVariant.product_id == product.id,
                        )
                        .values(deleted_at=now)
                    )
                event = await db.scalar(
                    select(CatalogWebhookEvent)
                    .where(
                        CatalogWebhookEvent.organization_id == organization_id,
                        CatalogWebhookEvent.id == event_id,
                    )
                    .with_for_update()
                )
                if event:
                    event.status = "succeeded"
                    event.completed_at = now
                await db.commit()
            return True
        snapshot = await ShopifyProductCatalogAdapter(resolve_credentials).get_product(
            ref, external_product_id=product_gid
        )
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            if snapshot is None:
                existing = await db.scalar(
                    select(CatalogProduct)
                    .where(
                        CatalogProduct.organization_id == organization_id,
                        CatalogProduct.connection_id == conn_id,
                        CatalogProduct.external_product_id == product_gid,
                    )
                    .with_for_update()
                )
                if existing:
                    existing.deleted_at = datetime.now(UTC)
            else:
                await upsert_product_snapshot(
                    db, organization_id=organization_id, connection_id=conn_id, snapshot=snapshot
                )
            event = await db.scalar(
                select(CatalogWebhookEvent)
                .where(
                    CatalogWebhookEvent.organization_id == organization_id,
                    CatalogWebhookEvent.id == event_id,
                )
                .with_for_update()
            )
            if event:
                event.status = "succeeded"
                event.completed_at = datetime.now(UTC)
            await db.commit()
        return True
    except (ShopifyAPIError, TimeoutError, OSError) as exc:
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            event = await db.scalar(
                select(CatalogWebhookEvent)
                .where(
                    CatalogWebhookEvent.organization_id == organization_id,
                    CatalogWebhookEvent.id == event_id,
                )
                .with_for_update()
            )
            if event:
                event.last_error_code = (
                    exc.code if isinstance(exc, ShopifyAPIError) else "provider_unavailable"
                )
                retryable = (
                    not isinstance(exc, ShopifyAPIError)
                    or exc.status_code == 429
                    or exc.status_code >= 500
                )
                if retryable:
                    event.attempt_count += 1
                if not retryable or event.attempt_count >= event.max_attempts:
                    event.status = "failed"
                    event.completed_at = datetime.now(UTC)
                else:
                    event.status = "queued"
                    event.next_attempt_at = datetime.now(UTC) + timedelta(
                        seconds=retry_delay_seconds(
                            event.attempt_count, base_seconds=30, cap_seconds=1800
                        )
                    )
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
        db.add(
            CatalogSyncJob(
                organization_id=organization_id,
                connection_id=connection.id,
                mode="reconcile",
                status="queued",
                attempt_count=0,
                max_attempts=MAX_SYNC_ATTEMPTS,
                next_attempt_at=now,
                updated_after=None,
            )
        )
        await db.commit()
        return True
