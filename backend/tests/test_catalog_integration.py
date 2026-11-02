import asyncio
import base64
import hashlib
import hmac
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, set_tenant_context
from app.integrations.core.contracts.catalog import CatalogProductSnapshot, CatalogVariantSnapshot
from app.models import (
    AIExecution,
    CatalogProduct,
    CatalogSyncJob,
    CatalogVariant,
    CatalogWebhookEvent,
    IntegrationConnection,
    IntegrationWebhookEvent,
    PlatformOwner,
    ShopifyInstallation,
)
from app.services.catalog import process_catalog_webhook, run_catalog_sync_page
from app.services.recommendations import load_candidates

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Catalog integration tests require isolated PostgreSQL",
)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_approved_tenant(client, prefix: str) -> dict:
    slug = f"{prefix}-{uuid4().hex[:10]}"
    email = f"{prefix}-{uuid4().hex[:10]}@example.com"
    password = "catalog-test-password-long-enough"
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"{prefix.title()} catalog workspace",
            "organization_slug": slug,
            "full_name": "Catalog Owner",
            "email": email,
            "password": password,
        },
    )
    assert registration.status_code == 202, registration.text
    platform_email = f"platform-{uuid4().hex[:10]}@example.com"
    platform_password = "catalog-test-platform-password"
    async with SessionLocal() as session:
        session.add(
            PlatformOwner(email=platform_email, password_hash=hash_password(platform_password))
        )
        await session.commit()
    platform_login = await client.post(
        "/api/v1/platform/auth/login",
        json={"email": platform_email, "password": platform_password},
    )
    assert platform_login.status_code == 200, platform_login.text
    platform_token = platform_login.json()["access_token"]
    pending = await client.get(
        "/api/v1/platform/tenants?approval_status=pending",
        headers=bearer(platform_token),
    )
    tenant = next(item for item in pending.json()["items"] if item["slug"] == slug)
    approved = await client.post(
        f"/api/v1/platform/tenants/{tenant['id']}/approve",
        headers=bearer(platform_token),
    )
    assert approved.status_code == 200, approved.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"organization_slug": slug, "email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return login.json()


async def create_catalog_product(session, owner: dict, suffix: str):
    organization_id = UUID(owner["user"]["organization_id"])
    user_id = UUID(owner["user"]["id"])
    await set_tenant_context(session, organization_id)
    shop_domain = f"{suffix}-{uuid4().hex[:10]}.myshopify.com"
    connection = IntegrationConnection(
        organization_id=organization_id,
        provider_id="shopify",
        external_account_id=shop_domain,
        display_name=suffix,
        status="connected",
        connected_by_user_id=user_id,
    )
    session.add(connection)
    await session.flush()
    session.add(
        ShopifyInstallation(
            organization_id=organization_id,
            shop_domain=shop_domain,
            auth_mode="oauth",
            access_token_encrypted="encrypted-access",
            refresh_token_encrypted="encrypted-refresh",
            granted_scopes=["read_orders", "read_customers", "read_products"],
            connected_by_user_id=user_id,
            connected_at=datetime.now(UTC),
        )
    )
    await session.flush()
    product = CatalogProduct(
        organization_id=organization_id,
        connection_id=connection.id,
        external_product_id=f"gid://shopify/Product/{uuid4().int % 100000}",
        title=f"{suffix} product",
        status="active",
        images=[],
        specifications={},
        synced_at=datetime.now(UTC),
    )
    session.add(product)
    await session.flush()
    return connection, product


async def create_connected_store(session, owner: dict):
    organization_id = UUID(owner["user"]["organization_id"])
    user_id = UUID(owner["user"]["id"])
    await set_tenant_context(session, organization_id)
    connection = IntegrationConnection(
        organization_id=organization_id,
        provider_id="shopify",
        external_account_id=f"catalog-{uuid4().hex[:8]}.myshopify.com",
        display_name="Catalog test store",
        status="connected",
        connected_by_user_id=user_id,
    )
    session.add(connection)
    session.add(
        ShopifyInstallation(
            organization_id=organization_id,
            shop_domain=connection.external_account_id,
            auth_mode="oauth",
            access_token_encrypted="encrypted-access",
            refresh_token_encrypted="encrypted-refresh",
            granted_scopes=["read_orders", "read_customers", "read_products"],
            connected_by_user_id=user_id,
            connected_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return connection


def product_node(price: str) -> dict:
    return {
        "id": "gid://shopify/Product/61001",
        "title": "Catalog sync product",
        "descriptionHtml": "<p>Useful item</p>",
        "status": "ACTIVE",
        "updatedAt": "2026-10-31T10:00:00Z",
        "variants": {
            "nodes": [
                {
                    "id": "gid://shopify/ProductVariant/61002",
                    "title": "Default",
                    "price": {"amount": price, "currencyCode": "USD"},
                    "availableForSale": True,
                    "selectedOptions": [],
                }
            ],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        },
    }


@pytest.mark.anyio
async def test_catalog_reads_are_tenant_scoped_and_composite_fk_rejects_cross_tenant_product(
    client,
):
    owner_a = await create_approved_tenant(client, "catalog-a")
    owner_b = await create_approved_tenant(client, "catalog-b")
    async with SessionLocal() as session:
        _connection_a, product_a = await create_catalog_product(session, owner_a, "shop-a")
        connection_b, _ = await create_catalog_product(session, owner_b, "shop-b")
        await session.commit()
        product_id = product_a.id

        await set_tenant_context(session, UUID(owner_b["user"]["organization_id"]))
        session.add(
            CatalogVariant(
                organization_id=UUID(owner_b["user"]["organization_id"]),
                product_id=product_id,
                connection_id=connection_b.id,
                external_variant_id="gid://shopify/ProductVariant/cross-tenant",
                title="Invalid cross-tenant variant",
                price=Decimal("10.00"),
                currency="USD",
                availability="available",
                attributes={},
                synced_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()

    read_a = await client.get("/api/v1/catalog/products", headers=bearer(owner_a["access_token"]))
    assert read_a.status_code == 200, read_a.text
    assert read_a.json()["total"] == 1
    assert read_a.json()["items"][0]["id"] == str(product_id)
    private_to_a = await client.get(
        f"/api/v1/catalog/products/{product_id}", headers=bearer(owner_b["access_token"])
    )
    assert private_to_a.status_code == 404


@pytest.mark.anyio
async def test_catalog_variant_cannot_reference_product_from_another_store_in_same_tenant(client):
    owner = await create_approved_tenant(client, "catalog-connection-fk")
    organization_id = UUID(owner["user"]["organization_id"])
    async with SessionLocal() as session:
        _connection_a, product_a = await create_catalog_product(session, owner, "store-a")
        connection_b = IntegrationConnection(
            organization_id=organization_id,
            provider_id="shopify",
            external_account_id=f"store-b-{uuid4().hex[:8]}.myshopify.com",
            display_name="Second store",
            status="connected",
            connected_by_user_id=UUID(owner["user"]["id"]),
        )
        session.add(connection_b)
        await session.flush()
        foreign_variant = CatalogVariant(
            organization_id=organization_id,
            product_id=product_a.id,
            connection_id=connection_b.id,
            external_variant_id=f"foreign-{uuid4().hex}",
            title="Cross-store variant",
            price=Decimal("10.00"),
            currency="USD",
            availability="available",
            attributes={},
            synced_at=datetime.now(UTC),
        )
        session.add(foreign_variant)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


@pytest.mark.anyio
async def test_catalog_upsert_is_idempotent_under_concurrent_first_insert(client):
    from app.services.catalog import upsert_product_snapshot

    owner = await create_approved_tenant(client, "catalog-upsert-race")
    organization_id = UUID(owner["user"]["organization_id"])
    async with SessionLocal() as session:
        connection = await create_connected_store(session, owner)
        connection_id = connection.id
        await session.commit()

    snapshot = CatalogProductSnapshot(
        external_product_id="gid://shopify/Product/concurrent",
        title="Concurrent product",
        status="active",
        variants=[
            CatalogVariantSnapshot(
                external_variant_id="gid://shopify/ProductVariant/concurrent",
                title="Default",
                price=Decimal("19.99"),
                currency="USD",
                availability="available",
            )
        ],
    )

    async def write_snapshot() -> None:
        async with SessionLocal() as session:
            await set_tenant_context(session, organization_id)
            await upsert_product_snapshot(
                session,
                organization_id=organization_id,
                connection_id=connection_id,
                snapshot=snapshot,
            )
            await session.commit()

    await asyncio.gather(write_snapshot(), write_snapshot())
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        products = await session.scalars(
            select(CatalogProduct).where(
                CatalogProduct.organization_id == organization_id,
                CatalogProduct.connection_id == connection_id,
                CatalogProduct.external_product_id == snapshot.external_product_id,
            )
        )
        product_rows = list(products.all())
        assert len(product_rows) == 1
        variants = await session.scalars(
            select(CatalogVariant).where(
                CatalogVariant.organization_id == organization_id,
                CatalogVariant.connection_id == connection_id,
                CatalogVariant.external_variant_id == "gid://shopify/ProductVariant/concurrent",
            )
        )
        assert len(list(variants.all())) == 1


@pytest.mark.anyio
async def test_catalog_status_surfaces_missing_product_scope_and_logs_no_credentials(
    client, caplog
):
    caplog.set_level(logging.INFO, logger="app.integrations.providers.shopify.client")
    owner = await create_approved_tenant(client, "catalog-scope")
    organization_id = UUID(owner["user"]["organization_id"])
    async with SessionLocal() as session:
        await create_catalog_product(session, owner, "catalog-scope")
        installation = await session.scalar(
            select(ShopifyInstallation).where(
                ShopifyInstallation.organization_id == organization_id
            )
        )
        assert installation is not None
        installation.granted_scopes = ["read_customers", "write_orders"]
        await session.commit()

    response = await client.get("/api/v1/catalog/status", headers=bearer(owner["access_token"]))
    assert response.status_code == 200, response.text
    assert response.json()["connected"] is True
    assert response.json()["product_scope_granted"] is False
    assert response.json()["product_count"] == 1
    assert '"event": "scope_check"' in caplog.text
    assert '"source": "catalog_status"' in caplog.text
    assert '"missing_catalog_scopes": ["read_products"]' in caplog.text
    assert "encrypted-access" not in caplog.text


@pytest.mark.anyio
async def test_catalog_sync_updates_price_and_partial_failure_preserves_last_good_data(
    client, monkeypatch
):
    from app.integrations.providers.shopify import catalog as shopify_catalog

    owner = await create_approved_tenant(client, "catalog-sync")
    organization_id = UUID(owner["user"]["organization_id"])
    async with SessionLocal() as session:
        connection = await create_connected_store(session, owner)
        now = datetime.now(UTC)
        job = CatalogSyncJob(
            organization_id=organization_id,
            connection_id=connection.id,
            mode="full",
            status="running",
            attempt_count=0,
            max_attempts=5,
            next_attempt_at=now,
            sync_started_at=now,
            started_at=now,
        )
        session.add(job)
        await session.commit()
        job_id = job.id
        connection_id = connection.id

    response_node = product_node("9.99")

    async def fake_graphql(*_args, **_kwargs):
        return {
            "products": {
                "nodes": [response_node],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }
        }

    async def credentials(_ref):
        return "catalog-test.myshopify.com", "private-token"

    monkeypatch.setattr(shopify_catalog, "graphql", fake_graphql)
    assert await run_catalog_sync_page(organization_id, job_id, resolve_credentials=credentials)
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        completed_job = await session.scalar(
            select(CatalogSyncJob).where(
                CatalogSyncJob.organization_id == organization_id,
                CatalogSyncJob.id == job_id,
            )
        )
        assert completed_job is not None
        assert completed_job.status == "succeeded"
        assert completed_job.records_seen == 1
        assert completed_job.last_error_code is None
        candidates, _, _ = await load_candidates(session, organization_id, "recommend product")
        assert len(candidates) == 1
        assert candidates[0].product.external_product_id == "gid://shopify/Product/61001"

    response_node = product_node("12.50")
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        next_job = CatalogSyncJob(
            organization_id=organization_id,
            connection_id=connection_id,
            mode="full",
            status="running",
            attempt_count=0,
            max_attempts=5,
            next_attempt_at=datetime.now(UTC),
            sync_started_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )
        session.add(next_job)
        await session.commit()
        next_job_id = next_job.id
    assert await run_catalog_sync_page(
        organization_id, next_job_id, resolve_credentials=credentials
    )

    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        product = await session.scalar(
            select(CatalogProduct).where(
                CatalogProduct.organization_id == organization_id,
                CatalogProduct.external_product_id == "gid://shopify/Product/61001",
            )
        )
        variant = await session.scalar(
            select(CatalogVariant).where(
                CatalogVariant.organization_id == organization_id,
                CatalogVariant.external_variant_id == "gid://shopify/ProductVariant/61002",
            )
        )
        assert product is not None and product.deleted_at is None
        assert variant is not None and variant.price == Decimal("12.50")
        failed_job = CatalogSyncJob(
            organization_id=organization_id,
            connection_id=connection_id,
            mode="full",
            status="running",
            attempt_count=0,
            max_attempts=5,
            next_attempt_at=datetime.now(UTC),
            sync_started_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
        )
        session.add(failed_job)
        await session.commit()
        failed_job_id = failed_job.id

    async def fail_graphql(*_args, **_kwargs):
        from app.integrations.providers.shopify.client import ShopifyAPIError

        raise ShopifyAPIError("shopify_unavailable", status_code=503)

    monkeypatch.setattr(shopify_catalog, "graphql", fail_graphql)
    assert await run_catalog_sync_page(
        organization_id, failed_job_id, resolve_credentials=credentials
    )
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        product = await session.scalar(
            select(CatalogProduct).where(
                CatalogProduct.organization_id == organization_id,
                CatalogProduct.external_product_id == "gid://shopify/Product/61001",
            )
        )
        assert product is not None and product.deleted_at is None
        current_variant = await session.scalar(
            select(CatalogVariant).where(
                CatalogVariant.organization_id == organization_id,
                CatalogVariant.product_id == product.id,
                CatalogVariant.deleted_at.is_(None),
            )
        )
        assert current_variant is not None and current_variant.price == Decimal("12.50")

        # A successful empty response is not a provider permission failure and
        # must clear an error from a prior attempt/job.
        empty_job = CatalogSyncJob(
            organization_id=organization_id,
            connection_id=connection_id,
            mode="full",
            status="running",
            attempt_count=0,
            max_attempts=5,
            next_attempt_at=datetime.now(UTC),
            sync_started_at=datetime.now(UTC),
            started_at=datetime.now(UTC),
            last_error_code="shopify_scope_or_data_access_required",
        )
        session.add(empty_job)
        await session.commit()
        empty_job_id = empty_job.id

    async def empty_graphql(*_args, **_kwargs):
        return {"products": {"nodes": [], "pageInfo": {"hasNextPage": False, "endCursor": None}}}

    monkeypatch.setattr(shopify_catalog, "graphql", empty_graphql)
    assert await run_catalog_sync_page(
        organization_id, empty_job_id, resolve_credentials=credentials
    )
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        empty_job_result = await session.scalar(
            select(CatalogSyncJob).where(
                CatalogSyncJob.organization_id == organization_id,
                CatalogSyncJob.id == empty_job_id,
            )
        )
        assert empty_job_result is not None
        assert empty_job_result.status == "succeeded"
        assert empty_job_result.records_seen == 0
        assert empty_job_result.last_error_code is None
    status_response = await client.get(
        "/api/v1/catalog/status", headers=bearer(owner["access_token"])
    )
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["product_count"] == 0
    assert status_response.json()["last_error_code"] is None

    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)

        delete_event = CatalogWebhookEvent(
            organization_id=organization_id,
            connection_id=connection_id,
            provider_id="shopify",
            external_event_id=f"test-delete-{uuid4().hex}",
            event_type="products/delete",
            external_product_id="gid://shopify/Product/61001",
            payload={},
            status="running",
            attempt_count=0,
            max_attempts=5,
            next_attempt_at=datetime.now(UTC),
        )
        session.add(delete_event)
        await session.commit()
        event_id = delete_event.id

    assert await process_catalog_webhook(
        organization_id,
        event_id,
        resolve_credentials=credentials,
    )
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        deleted = await session.scalar(
            select(CatalogProduct).where(
                CatalogProduct.organization_id == organization_id,
                CatalogProduct.external_product_id == "gid://shopify/Product/61001",
            )
        )
        assert deleted is not None and deleted.deleted_at is not None
        deleted_variant = await session.scalar(
            select(CatalogVariant).where(
                CatalogVariant.organization_id == organization_id,
                CatalogVariant.product_id == deleted.id,
            )
        )
        assert deleted_variant is not None and deleted_variant.deleted_at is not None


@pytest.mark.anyio
async def test_verified_shopify_product_webhook_is_deduplicated(client, monkeypatch):
    owner = await create_approved_tenant(client, "catalog-webhook")
    async with SessionLocal() as session:
        connection = await create_connected_store(session, owner)
        organization_id = UUID(owner["user"]["organization_id"])
        connection_id = connection.id
        shop_domain = connection.external_account_id
        await session.commit()
    secret_value = "catalog-webhook-test-secret"
    monkeypatch.setattr(
        settings,
        "shopify_client_secret",
        type("Secret", (), {"get_secret_value": lambda self: secret_value})(),
    )
    body = b'{"id":61003,"title":"Incoming product"}'
    signature = base64.b64encode(
        hmac.new(secret_value.encode(), body, hashlib.sha256).digest()
    ).decode()
    headers = {
        "x-shopify-hmac-sha256": signature,
        "x-shopify-topic": "products/create",
        "x-shopify-webhook-id": "catalog-webhook-delivery-1",
        "x-shopify-shop-domain": shop_domain,
        "content-type": "application/json",
    }
    endpoint = f"/api/v1/integrations/shopify/webhooks/catalog/{organization_id}/{connection_id}"

    first = await client.post(endpoint, content=body, headers=headers)
    duplicate = await client.post(endpoint, content=body, headers=headers)

    assert first.status_code == 200, first.text
    assert first.json() == {"accepted": True, "duplicate": False}
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json() == {"accepted": True, "duplicate": True}
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_id)
        events = await session.scalars(
            select(IntegrationWebhookEvent).where(
                IntegrationWebhookEvent.organization_id == organization_id,
                IntegrationWebhookEvent.connection_id == connection_id,
                IntegrationWebhookEvent.external_event_id == "catalog-webhook-delivery-1",
            )
        )
        event_rows = list(events.all())
        assert len(event_rows) == 1
        assert event_rows[0].normalized_payload == {
            "external_product_id": "gid://shopify/Product/61003",
            "shop_domain": shop_domain,
        }
        assert "Incoming product" not in str(event_rows[0].normalized_payload)


@pytest.mark.anyio
async def test_recommendation_execution_and_catalog_candidates_are_tenant_scoped(client):
    owner_a = await create_approved_tenant(client, "recommendation-a")
    owner_b = await create_approved_tenant(client, "recommendation-b")
    organization_a = UUID(owner_a["user"]["organization_id"])
    organization_b = UUID(owner_b["user"]["organization_id"])
    async with SessionLocal() as session:
        _, product_a = await create_catalog_product(session, owner_a, "recommendation-a")
        _, product_b = await create_catalog_product(session, owner_b, "recommendation-b")
        await session.commit()
        for organization_id, product in ((organization_a, product_a), (organization_b, product_b)):
            await set_tenant_context(session, organization_id)
            product.title = "Camera smartphone"
            product.brand = "Example"
            product.category = "Smartphones"
            session.add(
                CatalogVariant(
                    organization_id=organization_id,
                    product_id=product.id,
                    connection_id=product.connection_id,
                    external_variant_id=f"variant-{uuid4().hex}",
                    title="Standard",
                    attributes={"feature": "camera"},
                    price=Decimal(25000),
                    currency="NPR",
                    availability="available",
                    synced_at=datetime.now(UTC),
                )
            )
            await session.commit()
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_b)
        visible, _, _ = await load_candidates(
            session, organization_b, "recommend smartphone camera"
        )
        assert visible
        assert {item.product.id for item in visible} == {product_b.id}

    created = await client.post(
        "/api/v1/recommendations",
        json={"question": "Recommend a smartphone under NPR 30000"},
        headers=bearer(owner_a["access_token"]),
    )
    assert created.status_code == 202, created.text
    execution_id = created.json()["id"]
    async with SessionLocal() as session:
        await set_tenant_context(session, organization_a)
        execution = await session.scalar(
            select(AIExecution).where(AIExecution.id == UUID(execution_id))
        )
        assert (
            execution is not None
            and execution.kind == "recommendation"
            and execution.status == "queued"
        )
    denied = await client.get(
        f"/api/v1/recommendations/{execution_id}",
        headers=bearer(owner_b["access_token"]),
    )
    assert denied.status_code == 404
