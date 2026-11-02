"""Shopify connection workflows that coordinate provider, credential and persistence services."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import set_tenant_context
from app.integrations.connections.service import sync_shopify_connection
from app.integrations.providers.shopify.client import (
    ShopifyAPIError,
    effective_shopify_scopes,
    log_shopify_event,
    request_oauth_token,
    resolve_token_scopes,
)
from app.integrations.providers.shopify.security import (
    REQUIRED_SCOPES,
    encrypt_credential,
    hash_oauth_state,
    normalize_shop_domain,
    validate_callback_timestamp,
    verify_callback_hmac,
)
from app.models import ShopifyInstallation, ShopifyOAuthState, User
from app.services.shopify_access import shopify_callback_return_url
from app.services.shopify_errors import to_api_error
from app.services.shopify_tokens import require_oauth_configuration

logger = logging.getLogger(__name__)
OAUTH_STATE_TTL = timedelta(minutes=10)


async def complete_shopify_oauth(
    query_items: list[tuple[str, str]],
    state: str,
    shop: str,
    hmac_value: str,
    timestamp: str,
    code: str,
    db: AsyncSession,
    user: User,
) -> str:
    client_id, client_secret = require_oauth_configuration()
    if not validate_callback_timestamp(timestamp):
        log_shopify_event(
            "oauth_callback_rejected",
            organization_id=str(user.organization_id),
            reason="timestamp_invalid_or_expired",
        )
        raise HTTPException(status_code=403, detail="Shopify authorization callback expired")
    if len({key for key, _ in query_items}) != len(query_items) or not verify_callback_hmac(
        query_items, hmac_value
    ):
        log_shopify_event(
            "oauth_callback_rejected",
            organization_id=str(user.organization_id),
            reason="signature_invalid_or_duplicate_parameters",
        )
        raise HTTPException(status_code=403, detail="Shopify authorization signature is invalid")
    try:
        normalized_shop = normalize_shop_domain(shop)
    except ValueError as exc:
        log_shopify_event(
            "oauth_callback_rejected",
            organization_id=str(user.organization_id),
            reason="shop_domain_invalid",
        )
        raise HTTPException(status_code=403, detail="Shopify store domain is invalid") from exc

    oauth_state = await db.scalar(
        select(ShopifyOAuthState)
        .where(
            ShopifyOAuthState.organization_id == user.organization_id,
            ShopifyOAuthState.user_id == user.id,
            ShopifyOAuthState.shop_domain == normalized_shop,
            ShopifyOAuthState.state_hash == hash_oauth_state(state),
            ShopifyOAuthState.consumed_at.is_(None),
            ShopifyOAuthState.expires_at > datetime.now(UTC),
        )
        .with_for_update()
    )
    if oauth_state is None:
        log_shopify_event(
            "oauth_callback_rejected",
            organization_id=str(user.organization_id),
            shop_domain=normalized_shop,
            reason="state_invalid_expired_or_reused",
        )
        raise HTTPException(
            status_code=403, detail="Shopify authorization state is invalid or already used"
        )
    oauth_state.consumed_at = datetime.now(UTC)
    await db.commit()
    await set_tenant_context(db, user.organization_id)
    log_shopify_event(
        "oauth_callback_validated",
        organization_id=str(user.organization_id),
        user_id=str(user.id),
        shop_domain=normalized_shop,
    )

    try:
        token = await request_oauth_token(
            normalized_shop,
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "expiring": "1",
            },
        )
    except ShopifyAPIError as exc:
        log_shopify_event(
            "oauth_connect_failed",
            organization_id=str(user.organization_id),
            shop_domain=normalized_shop,
            error_code=exc.code,
            provider_error_code=exc.reason_code,
            provider_status_code=exc.status_code,
        )
        raise to_api_error(exc) from exc
    access_token = token.get("access_token")
    refresh_token = token.get("refresh_token")
    expires_in = token.get("expires_in")
    refresh_expires_in = token.get("refresh_token_expires_in")
    try:
        granted_scopes, scope_source = await resolve_token_scopes(normalized_shop, token)
    except ShopifyAPIError as exc:
        log_shopify_event(
            "oauth_connect_scope_check_failed",
            organization_id=str(user.organization_id),
            shop_domain=normalized_shop,
            error_code=exc.code,
            provider_status_code=exc.status_code,
        )
        raise to_api_error(exc) from exc
    log_shopify_event(
        "oauth_connect_scopes_verified",
        organization_id=str(user.organization_id),
        shop_domain=normalized_shop,
        granted_scopes=granted_scopes,
        effective_scopes=sorted(effective_shopify_scopes(granted_scopes)),
        scope_source=scope_source,
    )
    if (
        not isinstance(access_token, str)
        or not isinstance(refresh_token, str)
        or not isinstance(expires_in, int)
        or not isinstance(refresh_expires_in, int)
    ):
        log_shopify_event(
            "oauth_connect_failed",
            organization_id=str(user.organization_id),
            shop_domain=normalized_shop,
            reason="invalid_offline_token_metadata",
            response_fields=sorted(token.keys()),
            access_token_present=isinstance(access_token, str) and bool(access_token),
            refresh_token_present=isinstance(refresh_token, str) and bool(refresh_token),
        )
        raise HTTPException(
            status_code=502, detail="Shopify returned invalid offline-token metadata"
        )
    effective_scopes = effective_shopify_scopes(granted_scopes)
    missing_scopes = set(REQUIRED_SCOPES) - effective_scopes
    if missing_scopes:
        log_shopify_event(
            "oauth_connect_failed",
            organization_id=str(user.organization_id),
            shop_domain=normalized_shop,
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
        values = {
            "shop_domain": normalized_shop,
            "auth_mode": "oauth",
            "access_token_encrypted": encrypt_credential(access_token),
            "refresh_token_encrypted": encrypt_credential(refresh_token),
            "access_token_expires_at": now + timedelta(seconds=expires_in),
            "refresh_token_expires_at": now + timedelta(seconds=refresh_expires_in),
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
        await sync_shopify_connection(db, installation)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="This Shopify store is already connected to another workspace"
        ) from exc
    except RuntimeError as exc:
        await db.rollback()
        log_shopify_event(
            "oauth_connect_failed",
            organization_id=str(user.organization_id),
            shop_domain=normalized_shop,
            reason="credential_encryption_unavailable",
        )
        raise HTTPException(
            status_code=503, detail="Shopify credential encryption is unavailable"
        ) from exc
    log_shopify_event(
        "oauth_connect_completed",
        organization_id=str(user.organization_id),
        user_id=str(user.id),
        shop_domain=normalized_shop,
        auth_mode="oauth",
        granted_scopes=granted_scopes,
        access_token_persisted=True,
        refresh_token_persisted=True,
        expires_in=expires_in,
        refresh_token_expires_in=refresh_expires_in,
    )
    return shopify_callback_return_url("connected")
