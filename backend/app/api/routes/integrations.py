import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.db.session import get_db
from app.integrations.connections.service import sync_shopify_connection
from app.integrations.providers.shopify.client import (
    effective_shopify_scopes,
    log_shopify_event,
)
from app.integrations.providers.shopify.security import (
    PRODUCT_CATALOG_SCOPES,
    REQUIRED_SCOPES,
    hash_oauth_state,
    make_authorization_url,
    normalize_shop_domain,
)
from app.models import ShopifyInstallation, ShopifyOAuthState, User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.shopify import (
    ShopifyIntegrationEventOut,
    ShopifyStatusOut,
)
from app.services.shopify_access import (
    client_credentials_is_available,
    oauth_is_configured,
)
from app.services.shopify_configured_connection import (
    connect_configured_shopify_store as connect_configured_shopify_store_service,
)
from app.services.shopify_oauth_flow import complete_shopify_oauth
from app.services.shopify_tokens import require_oauth_configuration

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/integrations/shopify", tags=["Shopify integration"], responses=COMMON_ERROR_RESPONSES
)
OAUTH_STATE_TTL = timedelta(minutes=10)


@router.get("/status", response_model=ShopifyStatusOut)
async def shopify_status(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ShopifyStatusOut:
    installation = await db.scalar(
        select(ShopifyInstallation).where(
            ShopifyInstallation.organization_id == user.organization_id
        )
    )
    connected = bool(
        installation
        and installation.disconnected_at is None
        and installation.access_token_encrypted
        and (installation.auth_mode == "client_credentials" or installation.refresh_token_encrypted)
    )
    if not connected:
        return ShopifyStatusOut(
            configured=oauth_is_configured(),
            connected=False,
            client_credentials_available=client_credentials_is_available(),
            configured_store_domain=settings.shopify_store_domain
            if client_credentials_is_available()
            else None,
        )
    missing_scopes = set(REQUIRED_SCOPES) - effective_shopify_scopes(installation.granted_scopes)
    effective_scopes = effective_shopify_scopes(installation.granted_scopes)
    catalog_missing_scopes = set(PRODUCT_CATALOG_SCOPES) - effective_scopes
    log_shopify_event(
        "scope_check",
        source="integration_status",
        organization_id=str(user.organization_id),
        shop_domain=installation.shop_domain,
        granted_scopes=sorted(installation.granted_scopes or []),
        effective_scopes=sorted(effective_scopes),
        required_order_scopes=sorted(REQUIRED_SCOPES),
        missing_order_scopes=sorted(missing_scopes),
        required_catalog_scopes=sorted(PRODUCT_CATALOG_SCOPES),
        missing_catalog_scopes=sorted(catalog_missing_scopes),
    )
    return ShopifyStatusOut(
        configured=oauth_is_configured(),
        connected=True,
        client_credentials_available=client_credentials_is_available(),
        configured_store_domain=settings.shopify_store_domain
        if client_credentials_is_available()
        else None,
        shop_domain=installation.shop_domain,
        granted_scopes=installation.granted_scopes,
        connected_at=installation.connected_at,
        access_token_expires_at=installation.access_token_expires_at,
        reconnect_required=bool(missing_scopes)
        or (installation.auth_mode == "oauth" and not oauth_is_configured()),
    )


@router.post("/connect-configured-store", response_model=ShopifyStatusOut)
async def connect_configured_shopify_store(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> ShopifyStatusOut:
    return await connect_configured_shopify_store_service(db, user)


@router.get("/connect")
async def connect_shopify(
    shop: str = Query(min_length=1, max_length=255),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> RedirectResponse:
    require_oauth_configuration()
    try:
        normalized_shop = normalize_shop_domain(shop)
        state = secrets.token_urlsafe(32)
        authorization_url = make_authorization_url(normalized_shop, state)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    log_shopify_event(
        "oauth_authorization_started",
        organization_id=str(user.organization_id),
        user_id=str(user.id),
        shop_domain=normalized_shop,
        requested_scopes=[*REQUIRED_SCOPES, *PRODUCT_CATALOG_SCOPES],
        redirect_host=urlsplit(settings.shopify_redirect_uri or "").hostname,
    )
    db.add(
        ShopifyOAuthState(
            organization_id=user.organization_id,
            user_id=user.id,
            shop_domain=normalized_shop,
            state_hash=hash_oauth_state(state),
            expires_at=datetime.now(UTC) + OAUTH_STATE_TTL,
        )
    )
    await db.flush()
    return RedirectResponse(authorization_url, status_code=status.HTTP_302_FOUND)


@router.get("/callback")
async def shopify_callback(
    request: Request,
    state: str = Query(min_length=16, max_length=256),
    shop: str = Query(min_length=1, max_length=255),
    hmac_value: str = Query(alias="hmac", min_length=64, max_length=64),
    timestamp: str = Query(min_length=1, max_length=16),
    code: str = Query(min_length=1, max_length=512),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> RedirectResponse:
    target = await complete_shopify_oauth(
        query_items=request.query_params.multi_items(),
        state=state,
        shop=shop,
        hmac_value=hmac_value,
        timestamp=timestamp,
        code=code,
        db=db,
        user=user,
    )
    return RedirectResponse(target, status_code=303)


@router.post("/disconnect", response_model=ShopifyIntegrationEventOut)
async def disconnect_shopify(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> ShopifyIntegrationEventOut:
    installation = await db.scalar(
        select(ShopifyInstallation)
        .where(ShopifyInstallation.organization_id == user.organization_id)
        .with_for_update()
    )
    if installation is None or installation.disconnected_at is not None:
        return ShopifyIntegrationEventOut(
            status="disconnected", message="No Shopify store is connected"
        )
    shop_domain = installation.shop_domain
    installation.disconnected_at = datetime.now(UTC)
    installation.access_token_encrypted = None
    installation.refresh_token_encrypted = None
    installation.access_token_expires_at = None
    installation.refresh_token_expires_at = None
    installation.granted_scopes = []
    await sync_shopify_connection(db, installation)
    return ShopifyIntegrationEventOut(
        status="disconnected",
        message="Shopify access credentials were removed",
        shop_domain=shop_domain,
    )
