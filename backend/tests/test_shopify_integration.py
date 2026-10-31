import hashlib
import hmac
import os
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, set_tenant_context
from app.models import PlatformOwner, ShopifyAccessAudit, ShopifyInstallation
from app.services.shopify_security import decrypt_credential

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="Shopify integration tests require isolated PostgreSQL",
)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def approved_workspace(client, label: str):
    suffix = uuid4().hex[:10]
    slug = f"{label}-{suffix}"
    email = f"{label}-{suffix}@example.com"
    password = "shopify-owner-test-password"
    registration = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": f"{label.title()} Workspace",
            "organization_slug": slug,
            "full_name": "Shopify Workspace Owner",
            "email": email,
            "password": password,
        },
    )
    assert registration.status_code == 202, registration.text
    platform_email = f"platform-{suffix}@example.com"
    platform_password = "shopify-platform-test-password"
    async with SessionLocal() as db:
        db.add(PlatformOwner(email=platform_email, password_hash=hash_password(platform_password)))
        await db.commit()
    platform_login = await client.post(
        "/api/v1/platform/auth/login",
        json={"email": platform_email, "password": platform_password},
    )
    pending = await client.get(
        "/api/v1/platform/tenants?approval_status=pending",
        headers=bearer(platform_login.json()["access_token"]),
    )
    tenant = next(row for row in pending.json()["items"] if row["slug"] == slug)
    approved = await client.post(
        f"/api/v1/platform/tenants/{tenant['id']}/approve",
        headers=bearer(platform_login.json()["access_token"]),
    )
    assert approved.status_code == 200, approved.text
    login = await client.post(
        "/api/v1/auth/login",
        json={"organization_slug": slug, "email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    return login.json()


def signed_callback_params(state: str, shop: str, code: str) -> dict[str, str]:
    params = {
        "code": code,
        "shop": shop,
        "state": state,
        "timestamp": str(int(time.time())),
    }
    canonical = "&".join(f"{key}={value}" for key, value in sorted(params.items()))
    params["hmac"] = hmac.new(
        settings.shopify_client_secret.get_secret_value().encode(),
        canonical.encode(),
        hashlib.sha256,
    ).hexdigest()
    return params


class MockOrderProvider:
    @staticmethod
    def order(order_name: str, email: str, *, gid: str = "gid://shopify/Order/1001"):
        return {
            "id": gid,
            "name": order_name,
            "createdAt": "2026-10-30T12:00:00Z",
            "displayFinancialStatus": "PAID",
            "displayFulfillmentStatus": "FULFILLED",
            "currentTotalPriceSet": {"shopMoney": {"amount": "42.50", "currencyCode": "USD"}},
            "customer": {"id": "gid://shopify/Customer/42", "displayName": "Morgan Buyer", "email": email},
            "fulfillments": [{"trackingInfo": [{"company": "UPS", "number": "1Z999", "url": "https://track.example/1Z999"}]}],
        }


@pytest.mark.anyio
async def test_shopify_oauth_scope_tenant_isolation_lookup_verification_and_disconnect(client, monkeypatch):
    owner = await approved_workspace(client, "shopify")
    organization_id = UUID(owner["user"]["organization_id"])
    secret = "shopify-test-client-secret"
    encryption_key = ""
    try:
        from cryptography.fernet import Fernet
        encryption_key = Fernet.generate_key().decode("ascii")
    except ImportError:
        pytest.skip("cryptography dependency is required for Shopify credential tests")
    monkeypatch.setattr(settings, "shopify_client_id", "test-shopify-client")
    monkeypatch.setattr(settings, "shopify_client_secret", SecretStr(secret))
    monkeypatch.setattr(settings, "shopify_redirect_uri", "https://supportpilot.example/api/integrations/shopify/callback")
    monkeypatch.setattr(settings, "shopify_encryption_key", SecretStr(encryption_key))
    monkeypatch.setattr(settings, "shopify_api_version", "2026-10")

    status_before = await client.get(
        "/api/v1/integrations/shopify/status", headers=bearer(owner["access_token"])
    )
    assert status_before.status_code == 200
    assert status_before.json() == {
        "configured": True,
        "connected": False,
        "client_credentials_available": False,
        "configured_store_domain": None,
        "shop_domain": None,
        "granted_scopes": [],
        "connected_at": None,
        "access_token_expires_at": None,
        "reconnect_required": False,
    }

    connect = await client.get(
        "/api/v1/integrations/shopify/connect?shop=demo-store.myshopify.com",
        headers=bearer(owner["access_token"]),
    )
    assert connect.status_code == 302
    auth_url = urlsplit(connect.headers["location"])
    assert auth_url.netloc == "demo-store.myshopify.com"
    assert parse_qs(auth_url.query)["scope"] == ["read_orders,read_customers"]
    state = parse_qs(auth_url.query)["state"][0]

    async def mock_token(shop_domain, data):
        assert shop_domain == "demo-store.myshopify.com"
        assert data["expiring"] == "1"
        return {
            "access_token": "shopify-access-secret",
            "refresh_token": "shopify-refresh-secret",
            "expires_in": 3600,
            "refresh_token_expires_in": 7776000,
            "scope": "read_customers,read_orders",
        }

    monkeypatch.setattr("app.api.routes.integrations.request_oauth_token", mock_token)
    callback = await client.get(
        "/api/v1/integrations/shopify/callback",
        params=signed_callback_params(state, "demo-store.myshopify.com", "one-time-code"),
        headers=bearer(owner["access_token"]),
    )
    assert callback.status_code == 303
    assert callback.headers["location"] == "https://supportpilot.example/dashboard/settings?shopify=connected"
    replay = await client.get(
        "/api/v1/integrations/shopify/callback",
        params=signed_callback_params(state, "demo-store.myshopify.com", "one-time-code"),
        headers=bearer(owner["access_token"]),
    )
    assert replay.status_code == 403

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        installation = await db.get(ShopifyInstallation, organization_id)
        assert installation is not None
        assert installation.access_token_encrypted != "shopify-access-secret"
        assert installation.refresh_token_encrypted != "shopify-refresh-secret"
        await db.rollback()

    status_connected = await client.get(
        "/api/v1/integrations/shopify/status", headers=bearer(owner["access_token"])
    )
    assert status_connected.status_code == 200
    assert status_connected.json()["connected"] is True
    assert status_connected.json()["granted_scopes"] == ["read_customers", "read_orders"]

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        installation = await db.get(ShopifyInstallation, organization_id)
        assert installation is not None
        installation.access_token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    async def mock_refresh(shop_domain, data):
        assert shop_domain == "demo-store.myshopify.com"
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "shopify-refresh-secret"
        return {
            "access_token": "shopify-rotated-access-secret",
            "refresh_token": "shopify-rotated-refresh-secret",
            "expires_in": 3600,
            "refresh_token_expires_in": 7776000,
            "scope": "read_customers,read_orders",
        }

    monkeypatch.setattr("app.api.routes.integrations.request_oauth_token", mock_refresh)

    async def mock_orders(shop_domain, access_token, *, search_query, limit, cursor):
        assert shop_domain == "demo-store.myshopify.com"
        assert access_token == "shopify-rotated-access-secret"
        if 'name:"#1001"' in search_query:
            return {"nodes": [MockOrderProvider.order("#1001", "morgan@example.com")], "page_info": {"hasNextPage": False, "endCursor": None}}
        return {
            "nodes": [
                MockOrderProvider.order("#1002", "morgan@example.com", gid="gid://shopify/Order/1002"),
                MockOrderProvider.order("#1001", "morgan@example.com"),
                MockOrderProvider.order("#1003", "someone-else@example.com", gid="gid://shopify/Order/1003"),
            ],
            "page_info": {"hasNextPage": True, "endCursor": "next-cursor"},
        }

    monkeypatch.setattr("app.api.routes.integrations.fetch_orders", mock_orders)
    monkeypatch.setattr("app.services.shopify_orders.fetch_orders", mock_orders)
    lookup = await client.get(
        "/api/v1/integrations/shopify/orders",
        params={"customer_email": "morgan@example.com", "order_number": "1001"},
        headers=bearer(owner["access_token"]),
    )
    assert lookup.status_code == 200, lookup.text
    assert lookup.json()["customer"]["verified_by"] == "order_number_and_email"
    assert lookup.json()["matched_order"]["order_number"] == "#1001"
    assert len(lookup.json()["recent_orders"]) == 2
    assert lookup.json()["recent_orders"][0]["tracking"][0]["number"] == "1Z999"

    async def mock_order_page(shop_domain, access_token, *, limit, cursor):
        assert shop_domain == "demo-store.myshopify.com"
        assert access_token == "shopify-rotated-access-secret"
        assert limit == 25
        assert cursor is None
        return {
            "nodes": [MockOrderProvider.order("#1002", "morgan@example.com")],
            "page_info": {"hasNextPage": True, "endCursor": "order-cursor"},
        }

    monkeypatch.setattr("app.api.routes.integrations.fetch_order_page", mock_order_page)
    listed = await client.get(
        "/api/v1/integrations/shopify/orders/list",
        headers=bearer(owner["access_token"]),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json() == {
        "items": [{
            "id": "gid://shopify/Order/1001",
            "order_number": "#1002",
            "created_at": "2026-10-30T12:00:00Z",
            "financial_status": "PAID",
            "fulfillment_status": "FULFILLED",
            "total_amount": "42.50",
            "currency": "USD",
        }],
        "has_next_page": True,
        "next_cursor": "order-cursor",
    }
    assert "customer" not in listed.json()["items"][0]

    wrong_email = await client.get(
        "/api/v1/integrations/shopify/orders",
        params={"customer_email": "wrong@example.com", "order_number": "1001"},
        headers=bearer(owner["access_token"]),
    )
    assert wrong_email.status_code == 404
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        audit = list(await db.scalars(select(ShopifyAccessAudit)))
        assert len(audit) == 3
        assert {item.details.get("verification", item.details.get("view")) for item in audit} == {
            "order_number_and_email",
            "not_verified",
            "orders_list",
        }
        assert sorted(item.result_count for item in audit) == [0, 1, 3]
        audit_data = str([(item.query_fingerprint, item.details) for item in audit])
        assert "morgan@example.com" not in audit_data
        assert "wrong@example.com" not in audit_data
        installation = await db.get(ShopifyInstallation, organization_id)
        assert installation is not None
        assert decrypt_credential(installation.access_token_encrypted) == "shopify-rotated-access-secret"
        assert decrypt_credential(installation.refresh_token_encrypted) == "shopify-rotated-refresh-secret"
        await db.rollback()

    other_owner = await approved_workspace(client, "shopify-other")
    other_status = await client.get(
        "/api/v1/integrations/shopify/status", headers=bearer(other_owner["access_token"])
    )
    assert other_status.status_code == 200
    assert other_status.json()["connected"] is False
    isolated_orders = await client.get(
        "/api/v1/integrations/shopify/orders",
        params={"customer_email": "morgan@example.com", "order_number": "1001"},
        headers=bearer(other_owner["access_token"]),
    )
    assert isolated_orders.status_code == 409

    disconnected = await client.post(
        "/api/v1/integrations/shopify/disconnect", headers=bearer(owner["access_token"])
    )
    assert disconnected.status_code == 200
    status_after = await client.get(
        "/api/v1/integrations/shopify/status", headers=bearer(owner["access_token"])
    )
    assert status_after.json()["connected"] is False
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        installation = await db.get(ShopifyInstallation, organization_id)
        assert installation is not None
        assert installation.access_token_encrypted is None
        assert installation.refresh_token_encrypted is None
        await db.rollback()


@pytest.mark.anyio
async def test_shopify_callback_rejects_invalid_hmac_and_shop_domain(client, monkeypatch):
    owner = await approved_workspace(client, "shopify-callback")
    secret = "shopify-test-client-secret"
    monkeypatch.setattr(settings, "shopify_client_id", "test-shopify-client")
    monkeypatch.setattr(settings, "shopify_client_secret", SecretStr(secret))
    monkeypatch.setattr(settings, "shopify_redirect_uri", "https://supportpilot.example/api/integrations/shopify/callback")
    monkeypatch.setattr(settings, "shopify_encryption_key", SecretStr("not-used-until-exchange"))
    connect = await client.get(
        "/api/v1/integrations/shopify/connect?shop=demo-store.myshopify.com",
        headers=bearer(owner["access_token"]),
    )
    state = parse_qs(urlsplit(connect.headers["location"]).query)["state"][0]
    calls = 0

    async def mock_token(*args, **kwargs):
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr("app.api.routes.integrations.request_oauth_token", mock_token)
    params = signed_callback_params(state, "demo-store.myshopify.com", "code")
    params["hmac"] = "0" * 64
    invalid_signature = await client.get(
        "/api/v1/integrations/shopify/callback", params=params, headers=bearer(owner["access_token"])
    )
    assert invalid_signature.status_code == 403
    assert calls == 0

    tampered = signed_callback_params(state, "demo-store.myshopify.com.attacker.test", "code")
    invalid_domain = await client.get(
        "/api/v1/integrations/shopify/callback", params=tampered, headers=bearer(owner["access_token"])
    )
    assert invalid_domain.status_code == 403
    assert calls == 0


@pytest.mark.anyio
async def test_configured_store_connection_uses_server_credentials_and_encrypts_token(client, monkeypatch):
    pytest.importorskip("cryptography")
    owner = await approved_workspace(client, "shopify-configured")
    organization_id = UUID(owner["user"]["organization_id"])
    from cryptography.fernet import Fernet

    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "shopify_store_domain", "supportpilot-demo-stor.myshopify.com")
    monkeypatch.setattr(settings, "shopify_client_id", "real-test-client-id")
    monkeypatch.setattr(settings, "shopify_client_secret", SecretStr("real-test-client-secret"))
    monkeypatch.setattr(settings, "shopify_encryption_key", SecretStr(Fernet.generate_key().decode("ascii")))
    calls = []

    async def mock_client_credentials(shop_domain):
        calls.append(shop_domain)
        return {
            "access_token": "private-short-lived-shopify-token",
            "expires_in": 86400,
            "scope": "read_customers,read_orders",
        }

    monkeypatch.setattr("app.api.routes.integrations.request_client_credentials_token", mock_client_credentials)
    response = await client.post(
        "/api/v1/integrations/shopify/connect-configured-store",
        headers=bearer(owner["access_token"]),
    )
    assert response.status_code == 200, response.text
    assert calls == ["supportpilot-demo-stor.myshopify.com"]
    assert response.json()["connected"] is True
    assert response.json()["shop_domain"] == "supportpilot-demo-stor.myshopify.com"

    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        installation = await db.get(ShopifyInstallation, organization_id)
        assert installation is not None
        assert installation.auth_mode == "client_credentials"
        assert installation.refresh_token_encrypted is None
        assert installation.access_token_encrypted != "private-short-lived-shopify-token"
        assert decrypt_credential(installation.access_token_encrypted) == "private-short-lived-shopify-token"
        await db.rollback()
