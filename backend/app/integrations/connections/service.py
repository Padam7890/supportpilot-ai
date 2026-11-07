"""Tenant-scoped integration connection and credential persistence helpers."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.credentials import (
    delete_connection_credentials,
    store_encrypted_credential,
)
from app.models import IntegrationConnection, IntegrationConnectionAudit, ShopifyInstallation

__all__ = ["disconnect_generic_connection", "record_connection_audit", "sync_shopify_connection"]


def record_connection_audit(
    db: AsyncSession,
    connection: IntegrationConnection,
    *,
    event_type: str,
    actor_user_id: UUID | None,
    auth_mode: str | None = None,
    granted_scopes: list[str] | None = None,
    previous_ai_agent_id: UUID | None = None,
    ai_agent_id: UUID | None = None,
) -> None:
    """Record secret-free lifecycle and bot-routing metadata in the current transaction."""
    if event_type not in {"connected", "reauthorized", "disconnected", "bot_routing_changed"}:
        raise ValueError("Unsupported integration connection audit event")
    details: dict[str, object] = {}
    if auth_mode:
        details["auth_mode"] = auth_mode
    if granted_scopes is not None:
        details["granted_scopes"] = sorted(set(granted_scopes))
    if event_type == "bot_routing_changed":
        details["previous_ai_agent_id"] = str(previous_ai_agent_id) if previous_ai_agent_id else None
        details["ai_agent_id"] = str(ai_agent_id) if ai_agent_id else None
    db.add(
        IntegrationConnectionAudit(
            organization_id=connection.organization_id,
            connection_id=connection.id,
            actor_user_id=actor_user_id,
            provider_id=connection.provider_id,
            event_type=event_type,
            details=details,
        )
    )


async def sync_shopify_connection(
    db: AsyncSession,
    installation: ShopifyInstallation,
) -> IntegrationConnection:
    """Mirror legacy Shopify state into the generic connection store.

    Ciphertext is copied unchanged during the compatibility period. This keeps
    the established encryption key and OAuth refresh behavior authoritative.
    """
    old_connections = (
        await db.scalars(
            select(IntegrationConnection)
            .where(
                IntegrationConnection.organization_id == installation.organization_id,
                IntegrationConnection.provider_id == "shopify",
                IntegrationConnection.external_account_id != installation.shop_domain,
                IntegrationConnection.status != "disconnected",
            )
            .with_for_update()
        )
    ).all()
    for old_connection in old_connections:
        old_connection.status = "disconnected"
        old_connection.last_error_code = None
        old_connection.updated_at = datetime.now(UTC)
        await delete_connection_credentials(
            db,
            organization_id=installation.organization_id,
            connection_id=old_connection.id,
        )

    connection = await db.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.organization_id == installation.organization_id,
            IntegrationConnection.provider_id == "shopify",
            IntegrationConnection.external_account_id == installation.shop_domain,
        )
        .with_for_update()
    )
    if connection is None:
        connection = IntegrationConnection(
            organization_id=installation.organization_id,
            provider_id="shopify",
            external_account_id=installation.shop_domain,
            display_name=installation.shop_domain,
            connected_by_user_id=installation.connected_by_user_id,
        )
        db.add(connection)
        await db.flush()

    disconnected = installation.disconnected_at is not None
    needs_reauth = not installation.access_token_encrypted or (
        installation.auth_mode == "oauth" and not installation.refresh_token_encrypted
    )
    connection.status = (
        "disconnected"
        if disconnected
        else "reauthorization_required"
        if needs_reauth
        else "connected"
    )
    connection.connected_by_user_id = installation.connected_by_user_id
    connection.connected_at = installation.connected_at
    connection.safe_configuration = {
        "auth_mode": installation.auth_mode,
        "granted_scopes": list(installation.granted_scopes or []),
    }
    connection.last_error_code = (
        "reauthorization_required" if needs_reauth and not disconnected else None
    )
    connection.updated_at = datetime.now(UTC)

    token_values = {
        "access_token": (installation.access_token_encrypted, installation.access_token_expires_at),
        "refresh_token": (
            installation.refresh_token_encrypted,
            installation.refresh_token_expires_at,
        ),
    }
    for credential_type, (encrypted_value, expires_at) in token_values.items():
        if disconnected or encrypted_value is None:
            await delete_connection_credentials(
                db,
                organization_id=installation.organization_id,
                connection_id=connection.id,
                credential_type=credential_type,
            )
            continue
        await store_encrypted_credential(
            db,
            organization_id=installation.organization_id,
            connection_id=connection.id,
            credential_type=credential_type,
            encrypted_value=encrypted_value,
            key_version="shopify_legacy_v1",
            expires_at=expires_at,
        )
    await db.flush()
    return connection


async def disconnect_generic_connection(
    db: AsyncSession,
    connection: IntegrationConnection,
) -> None:
    """Revoke a connection and erase credentials without deleting audit state."""
    if connection.provider_id == "shopify":
        installation = await db.scalar(
            select(ShopifyInstallation)
            .where(ShopifyInstallation.organization_id == connection.organization_id)
            .with_for_update()
        )
        if installation is not None and installation.shop_domain == connection.external_account_id:
            installation.disconnected_at = datetime.now(UTC)
            installation.access_token_encrypted = None
            installation.refresh_token_encrypted = None
            installation.access_token_expires_at = None
            installation.refresh_token_expires_at = None
            installation.granted_scopes = []
    await delete_connection_credentials(
        db,
        organization_id=connection.organization_id,
        connection_id=connection.id,
    )
    connection.status = "disconnected"
    connection.last_error_code = None
    connection.updated_at = datetime.now(UTC)
    await db.flush()
