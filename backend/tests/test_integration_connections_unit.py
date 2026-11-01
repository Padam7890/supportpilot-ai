from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.integrations.connections.service import (
    disconnect_generic_connection,
    sync_shopify_connection,
)
from app.models import IntegrationConnection, IntegrationCredential, ShopifyInstallation


def make_installation() -> ShopifyInstallation:
    now = datetime.now(UTC)
    return ShopifyInstallation(
        organization_id=uuid4(),
        shop_domain="supportpilot-test.myshopify.com",
        auth_mode="oauth",
        access_token_encrypted="ciphertext-access",
        refresh_token_encrypted="ciphertext-refresh",
        access_token_expires_at=now + timedelta(hours=1),
        refresh_token_expires_at=now + timedelta(days=20),
        granted_scopes=["read_customers", "write_orders"],
        connected_by_user_id=uuid4(),
        connected_at=now,
    )


@pytest.mark.anyio
async def test_sync_shopify_connection_copies_ciphertext_and_safe_metadata_only():
    installation = make_installation()
    connection = IntegrationConnection(
        id=uuid4(),
        organization_id=installation.organization_id,
        provider_id="shopify",
        external_account_id=installation.shop_domain,
        display_name=installation.shop_domain,
        connected_by_user_id=installation.connected_by_user_id,
        status="pending",
    )
    access = IntegrationCredential(
        id=uuid4(),
        organization_id=installation.organization_id,
        connection_id=connection.id,
        credential_type="access_token",
        encrypted_value="old-access-ciphertext",
        key_version="shopify_legacy_v1",
    )
    refresh = IntegrationCredential(
        id=uuid4(),
        organization_id=installation.organization_id,
        connection_id=connection.id,
        credential_type="refresh_token",
        encrypted_value="old-refresh-ciphertext",
        key_version="shopify_legacy_v1",
    )
    db = SimpleNamespace(
        scalar=AsyncMock(side_effect=[connection, access, refresh]),
        scalars=AsyncMock(
            return_value=SimpleNamespace(all=list)
        ),
        flush=AsyncMock(),
    )

    await sync_shopify_connection(db, installation)

    assert connection.status == "connected"
    assert connection.safe_configuration == {
        "auth_mode": "oauth",
        "granted_scopes": ["read_customers", "write_orders"],
    }
    assert access.encrypted_value == "ciphertext-access"
    assert access.expires_at == installation.access_token_expires_at
    assert refresh.encrypted_value == "ciphertext-refresh"
    assert refresh.expires_at == installation.refresh_token_expires_at
    assert "access_token" not in str(connection.safe_configuration)


@pytest.mark.anyio
async def test_disconnect_shopify_clears_legacy_and_generic_credentials():
    installation = make_installation()
    connection = IntegrationConnection(
        id=uuid4(),
        organization_id=installation.organization_id,
        provider_id="shopify",
        external_account_id=installation.shop_domain,
        display_name=installation.shop_domain,
        connected_by_user_id=installation.connected_by_user_id,
        status="connected",
    )
    credentials = [
        IntegrationCredential(
            id=uuid4(),
            organization_id=installation.organization_id,
            connection_id=connection.id,
            credential_type="access_token",
            encrypted_value="ciphertext-access",
            key_version="shopify_legacy_v1",
        )
    ]
    db = SimpleNamespace(
        scalar=AsyncMock(return_value=installation),
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: credentials)),
        delete=AsyncMock(),
        flush=AsyncMock(),
    )

    await disconnect_generic_connection(db, connection)

    assert connection.status == "disconnected"
    assert installation.disconnected_at is not None
    assert installation.access_token_encrypted is None
    assert installation.refresh_token_encrypted is None
    assert installation.granted_scopes == []
    db.delete.assert_awaited_once_with(credentials[0])
