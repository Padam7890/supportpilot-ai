"""Shopify access-token refresh and persistence application service."""

import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import set_tenant_context
from app.integrations.connections.service import sync_shopify_connection
from app.integrations.providers.shopify.client import (
    ShopifyAPIError,
    effective_shopify_scopes,
    log_shopify_event,
    request_client_credentials_token,
    request_oauth_token,
    resolve_token_scopes,
)
from app.integrations.providers.shopify.security import (
    REQUIRED_SCOPES,
    decrypt_credential,
    encrypt_credential,
)
from app.models import ShopifyInstallation
from app.services.shopify_access import credentials_are_placeholders
from app.services.shopify_errors import to_api_error

logger = logging.getLogger(__name__)
TOKEN_REFRESH_SKEW = timedelta(minutes=5)
PLACEHOLDER_CREDENTIALS = {"your-client-id", "your-client-secret", "change-me", "replace-me"}


def require_oauth_configuration() -> tuple[str, str]:
    if (
        not settings.shopify_client_id
        or settings.shopify_client_secret is None
        or not settings.shopify_redirect_uri
        or settings.shopify_encryption_key is None
        or credentials_are_placeholders()
    ):
        raise HTTPException(status_code=503, detail="Shopify integration is not configured")
    redirect = urlsplit(settings.shopify_redirect_uri)
    if (
        redirect.scheme != "https"
        or not redirect.hostname
        or redirect.username
        or redirect.password
        or redirect.query
        or redirect.fragment
    ):
        raise HTTPException(
            status_code=503,
            detail="Shopify OAuth callback must be an HTTPS URL without credentials or query parameters",
        )
    return settings.shopify_client_id, settings.shopify_client_secret.get_secret_value()


async def valid_access_token(db: AsyncSession, installation: ShopifyInstallation) -> str:
    now = datetime.now(UTC)
    if (
        installation.access_token_encrypted is not None
        and installation.access_token_expires_at is not None
        and installation.access_token_expires_at > now + TOKEN_REFRESH_SKEW
    ):
        try:
            return decrypt_credential(installation.access_token_encrypted)
        except RuntimeError as exc:
            logger.error(
                "Shopify token decryption failed",
                extra={"organization_id": str(installation.organization_id)},
            )
            raise HTTPException(
                status_code=503,
                detail="Shopify credentials cannot be accessed; reconnect the store",
            ) from exc

    if installation.auth_mode == "client_credentials":
        try:
            token = await request_client_credentials_token(installation.shop_domain)
        except ShopifyAPIError as exc:
            raise to_api_error(exc) from exc
        access_token = token.get("access_token")
        expires_in = token.get("expires_in")
        try:
            granted_scopes, scope_source = await resolve_token_scopes(
                installation.shop_domain, token
            )
        except ShopifyAPIError as exc:
            log_shopify_event(
                "token_refresh_scope_check_failed",
                organization_id=str(installation.organization_id),
                shop_domain=installation.shop_domain,
                error_code=exc.code,
                provider_status_code=exc.status_code,
            )
            raise to_api_error(exc) from exc
        if not isinstance(access_token, str) or not access_token or not isinstance(expires_in, int):
            raise HTTPException(status_code=502, detail="Shopify returned invalid token metadata")
        effective_scopes = effective_shopify_scopes(granted_scopes)
        if not set(REQUIRED_SCOPES).issubset(effective_scopes):
            raise HTTPException(
                status_code=403,
                detail="Shopify did not grant the required read_orders and read_customers scopes",
            )
        try:
            installation.access_token_encrypted = encrypt_credential(access_token)
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503, detail="Shopify credential encryption is unavailable"
            ) from exc
        installation.access_token_expires_at = now + timedelta(seconds=expires_in)
        installation.granted_scopes = granted_scopes
        await sync_shopify_connection(db, installation)
        await db.commit()
        await set_tenant_context(db, installation.organization_id)
        return access_token

    client_id, client_secret = require_oauth_configuration()
    if installation.refresh_token_encrypted is None:
        raise HTTPException(status_code=409, detail="Reconnect the Shopify store to continue")
    try:
        refresh_token = decrypt_credential(installation.refresh_token_encrypted)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail="Shopify credentials cannot be accessed; reconnect the store"
        ) from exc
    try:
        token = await request_oauth_token(
            installation.shop_domain,
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    except ShopifyAPIError as exc:
        if exc.status_code == 403:
            installation.disconnected_at = now
            installation.access_token_encrypted = None
            installation.refresh_token_encrypted = None
            await sync_shopify_connection(db, installation)
            await db.commit()
            raise HTTPException(
                status_code=409, detail="The Shopify refresh token expired; reconnect the store"
            ) from exc
        raise to_api_error(exc) from exc
    access_token = token.get("access_token")
    new_refresh = token.get("refresh_token")
    expires_in = token.get("expires_in")
    refresh_expires_in = token.get("refresh_token_expires_in")
    if (
        not all(isinstance(value, str) and value for value in (access_token, new_refresh))
        or not isinstance(expires_in, int)
        or not isinstance(refresh_expires_in, int)
    ):
        raise HTTPException(status_code=502, detail="Shopify returned invalid token metadata")
    try:
        installation.access_token_encrypted = encrypt_credential(access_token)
        installation.refresh_token_encrypted = encrypt_credential(new_refresh)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503, detail="Shopify credential encryption is unavailable"
        ) from exc
    installation.access_token_expires_at = now + timedelta(seconds=expires_in)
    installation.refresh_token_expires_at = now + timedelta(seconds=refresh_expires_in)
    try:
        installation.granted_scopes, scope_source = await resolve_token_scopes(
            installation.shop_domain, token
        )
    except ShopifyAPIError as exc:
        log_shopify_event(
            "token_refresh_scope_check_failed",
            organization_id=str(installation.organization_id),
            shop_domain=installation.shop_domain,
            error_code=exc.code,
            provider_status_code=exc.status_code,
        )
        raise to_api_error(exc) from exc
    log_shopify_event(
        "token_refresh_scopes_verified",
        organization_id=str(installation.organization_id),
        shop_domain=installation.shop_domain,
        granted_scopes=installation.granted_scopes,
        scope_source=scope_source,
    )
    # Persist the rotating pair before making a separate Admin API request.
    await sync_shopify_connection(db, installation)
    await db.commit()
    await set_tenant_context(db, installation.organization_id)
    return access_token
