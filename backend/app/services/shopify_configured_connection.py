"""Shopify connection workflows that coordinate provider, credential and persistence services."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.connections.service import record_connection_audit, sync_shopify_connection
from app.integrations.providers.shopify.client import (
    ShopifyAPIError,
    effective_shopify_scopes,
    log_shopify_event,
    request_client_credentials_token,
    resolve_token_scopes,
)
from app.integrations.providers.shopify.security import (
    PRODUCT_CATALOG_SCOPES,
    REQUIRED_SCOPES,
    encrypt_credential,
    normalize_shop_domain,
)
from app.models import ShopifyInstallation, User
from app.schemas.shopify import ShopifyStatusOut
from app.services.shopify_access import client_credentials_is_available, oauth_is_configured
from app.services.shopify_errors import to_api_error

logger = logging.getLogger(__name__)
OAUTH_STATE_TTL = timedelta(minutes=10)


async def connect_configured_shopify_store(db: AsyncSession, user: User) -> ShopifyStatusOut:
    """Connect the one configured Shopify development store without browser OAuth."""
    log_shopify_event(
        "configured_connect_started",
        organization_id=str(user.organization_id),
        user_id=str(user.id),
        configured_store_domain=settings.shopify_store_domain,
        client_id_configured=bool(settings.shopify_client_id),
        client_secret_configured=settings.shopify_client_secret is not None,
        encryption_key_configured=settings.shopify_encryption_key is not None,
    )
    if not client_credentials_is_available():
        log_shopify_event(
            "configured_connect_rejected",
            organization_id=str(user.organization_id),
            reason="development_credentials_unavailable",
        )
        raise HTTPException(
            status_code=503,
            detail="Configured-store connection is available only with valid development credentials",
        )
    try:
        shop_domain = normalize_shop_domain(settings.shopify_store_domain or "")
        token = await request_client_credentials_token(shop_domain)
    except ValueError as exc:
        raise HTTPException(
            status_code=503, detail="Configured Shopify store domain is invalid"
        ) from exc
    except ShopifyAPIError as exc:
        log_shopify_event(
            "configured_connect_failed",
            organization_id=str(user.organization_id),
            shop_domain=settings.shopify_store_domain,
            error_code=exc.code,
            provider_error_code=exc.reason_code,
            provider_status_code=exc.status_code,
        )
        raise to_api_error(exc) from exc
    access_token = token.get("access_token")
    expires_in = token.get("expires_in")
    try:
        granted_scopes, scope_source = await resolve_token_scopes(shop_domain, token)
    except ShopifyAPIError as exc:
        log_shopify_event(
            "configured_connect_scope_check_failed",
            organization_id=str(user.organization_id),
            shop_domain=shop_domain,
            error_code=exc.code,
            provider_status_code=exc.status_code,
        )
        raise to_api_error(exc) from exc
    log_shopify_event(
        "configured_connect_scopes_verified",
        organization_id=str(user.organization_id),
        shop_domain=shop_domain,
        granted_scopes=granted_scopes,
        effective_scopes=sorted(effective_shopify_scopes(granted_scopes)),
        scope_source=scope_source,
    )
    if not isinstance(access_token, str) or not access_token or not isinstance(expires_in, int):
        log_shopify_event(
            "configured_connect_failed",
            organization_id=str(user.organization_id),
            shop_domain=shop_domain,
            reason="invalid_token_metadata",
            response_fields=sorted(token.keys()),
            access_token_present=isinstance(access_token, str) and bool(access_token),
            expires_in=expires_in if isinstance(expires_in, int) else None,
        )
        raise HTTPException(status_code=502, detail="Shopify returned invalid token metadata")
    effective_scopes = effective_shopify_scopes(granted_scopes)
    log_shopify_event(
        "scope_check",
        source="configured_store_connect",
        organization_id=str(user.organization_id),
        shop_domain=shop_domain,
        granted_scopes=sorted(granted_scopes),
        effective_scopes=sorted(effective_scopes),
        required_order_scopes=sorted(REQUIRED_SCOPES),
        missing_order_scopes=sorted(set(REQUIRED_SCOPES) - effective_scopes),
        required_catalog_scopes=sorted(PRODUCT_CATALOG_SCOPES),
        missing_catalog_scopes=sorted(set(PRODUCT_CATALOG_SCOPES) - effective_scopes),
    )
    missing_scopes = set(REQUIRED_SCOPES) - effective_scopes
    if missing_scopes:
        log_shopify_event(
            "configured_connect_failed",
            organization_id=str(user.organization_id),
            shop_domain=shop_domain,
            reason="required_scopes_missing",
            granted_scopes=granted_scopes,
            effective_scopes=sorted(effective_scopes),
            required_scopes=list(REQUIRED_SCOPES),
            missing_scopes=sorted(missing_scopes),
        )
        raise HTTPException(
            status_code=403,
            detail="Shopify did not grant the required read_orders and read_customers scopes",
        )
    now = datetime.now(UTC)
    try:
        installation = await db.scalar(
            select(ShopifyInstallation)
            .where(ShopifyInstallation.organization_id == user.organization_id)
            .with_for_update()
        )
        was_connected = bool(
            installation is not None
            and installation.disconnected_at is None
            and installation.access_token_encrypted
        )
        values = {
            "shop_domain": shop_domain,
            "auth_mode": "client_credentials",
            "access_token_encrypted": encrypt_credential(access_token),
            "refresh_token_encrypted": None,
            "access_token_expires_at": now + timedelta(seconds=expires_in),
            "refresh_token_expires_at": None,
            "granted_scopes": granted_scopes,
            "connected_by_user_id": user.id,
            "connected_at": now,
            "disconnected_at": None,
        }
        if installation is None:
            installation = ShopifyInstallation(organization_id=user.organization_id, **values)
            db.add(installation)
        else:
            for key, value in values.items():
                setattr(installation, key, value)
        await db.flush()
        connection = await sync_shopify_connection(db, installation)
        record_connection_audit(
            db,
            connection,
            event_type="reauthorized" if was_connected else "connected",
            actor_user_id=user.id,
            auth_mode=installation.auth_mode,
            granted_scopes=list(installation.granted_scopes or []),
        )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="This Shopify store is already connected to another workspace"
        ) from exc
    except RuntimeError as exc:
        await db.rollback()
        log_shopify_event(
            "configured_connect_failed",
            organization_id=str(user.organization_id),
            shop_domain=shop_domain,
            reason="credential_encryption_unavailable",
        )
        raise HTTPException(
            status_code=503, detail="Shopify credential encryption is unavailable"
        ) from exc
    log_shopify_event(
        "configured_connect_completed",
        organization_id=str(user.organization_id),
        user_id=str(user.id),
        shop_domain=shop_domain,
        auth_mode="client_credentials",
        granted_scopes=granted_scopes,
        access_token_persisted=True,
        expires_in=expires_in,
    )
    return ShopifyStatusOut(
        configured=oauth_is_configured(),
        connected=True,
        client_credentials_available=True,
        configured_store_domain=shop_domain,
        shop_domain=shop_domain,
        granted_scopes=granted_scopes,
        connected_at=now,
        access_token_expires_at=now + timedelta(seconds=expires_in),
        reconnect_required=False,
    )
