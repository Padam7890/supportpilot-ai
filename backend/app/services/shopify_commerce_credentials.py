"""Resolve current, tenant-owned credentials for Shopify commerce reads."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select

from app.db.session import SessionLocal, set_tenant_context
from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.providers.shopify.client import (
    ShopifyAPIError,
    effective_shopify_scopes,
    log_shopify_api_event,
)
from app.integrations.providers.shopify.commerce import VERIFIED_ORDER_READ_SCOPES
from app.models import IntegrationConnection, ShopifyInstallation


async def resolve_shopify_commerce_credentials(
    connection_ref: IntegrationConnectionRef,
) -> tuple[str, str, frozenset[str]]:
    """Verify the tenant connection and resolve its current token without logging it."""
    async with SessionLocal() as db:
        await set_tenant_context(db, connection_ref.organization_id)
        connection = await db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.id == connection_ref.id,
                IntegrationConnection.organization_id == connection_ref.organization_id,
                IntegrationConnection.provider_id == "shopify",
                IntegrationConnection.external_account_id == connection_ref.external_account_id,
                IntegrationConnection.status == "connected",
            )
        )
        installation = await db.scalar(
            select(ShopifyInstallation).where(
                ShopifyInstallation.organization_id == connection_ref.organization_id,
                ShopifyInstallation.disconnected_at.is_(None),
            ).with_for_update()
        )
        if (
            connection is None
            or installation is None
            or installation.shop_domain != connection_ref.external_account_id
            or not installation.access_token_encrypted
        ):
            raise ShopifyAPIError("shopify_connection_unavailable", status_code=409)

        try:
            from app.services.shopify_tokens import valid_access_token

            access_token = await valid_access_token(db, installation)
        except HTTPException as exc:
            error_code = (
                "shopify_required_scopes_missing"
                if exc.status_code == 403
                else "shopify_reauthorization_required"
                if exc.status_code == 409
                else "shopify_credentials_unavailable"
                if exc.status_code == 503
                else "shopify_authorization_failed"
            )
            log_shopify_api_event(
                "commerce_credentials_rejected",
                organization_id=str(connection_ref.organization_id),
                connection_id=str(connection_ref.id),
                shop_domain=installation.shop_domain,
                error_code=error_code,
                provider_status_code=exc.status_code,
            )
            raise ShopifyAPIError(error_code, status_code=exc.status_code) from None

        scopes = frozenset(effective_shopify_scopes(installation.granted_scopes or []))
        missing = VERIFIED_ORDER_READ_SCOPES.difference(scopes)
        if missing:
            raise ShopifyAPIError(
                "shopify_required_scopes_missing",
                status_code=403,
                reason_code=",".join(sorted(missing)),
            )

        token_was_current = bool(
            installation.access_token_expires_at
            and installation.access_token_expires_at > datetime.now(UTC) + timedelta(minutes=5)
        )
        log_shopify_api_event(
            "commerce_credentials_resolved",
            organization_id=str(connection_ref.organization_id),
            connection_id=str(connection_ref.id),
            shop_domain=installation.shop_domain,
            token_source="cached" if token_was_current else "refreshed",
            effective_scopes=sorted(scopes),
        )
        await db.commit()
        return installation.shop_domain, access_token, scopes
