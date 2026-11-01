import hashlib
import hmac
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import EmailStr
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.db.session import get_db, set_tenant_context
from app.integrations.connections.service import sync_shopify_connection
from app.integrations.providers.shopify.client import (
    ShopifyAPIError,
    effective_shopify_scopes,
    fetch_order_page,
    fetch_orders,
    log_shopify_api_event,
    log_shopify_event,
    request_client_credentials_token,
    request_oauth_token,
    resolve_token_scopes,
)
from app.integrations.providers.shopify.orders import lookup_authorized_order
from app.integrations.providers.shopify.security import (
    PRODUCT_CATALOG_SCOPES,
    REQUIRED_SCOPES,
    decrypt_credential,
    encrypt_credential,
    hash_oauth_state,
    make_authorization_url,
    normalize_shop_domain,
    validate_callback_timestamp,
    verify_callback_hmac,
)
from app.models import ShopifyAccessAudit, ShopifyInstallation, ShopifyOAuthState, User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.shopify import (
    ShopifyCustomerOut,
    ShopifyIntegrationEventOut,
    ShopifyOrderLookupOut,
    ShopifyOrderOut,
    ShopifyOrderPageOut,
    ShopifyOrderSummaryOut,
    ShopifyStatusOut,
    ShopifyTrackingOut,
)

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/integrations/shopify", tags=["Shopify integration"], responses=COMMON_ERROR_RESPONSES
)
OAUTH_STATE_TTL = timedelta(minutes=10)
TOKEN_REFRESH_SKEW = timedelta(minutes=5)
ORDER_NUMBER = re.compile(r"^#?[A-Za-z0-9-]+$")
PLACEHOLDER_CREDENTIALS = {"your-client-id", "your-client-secret", "change-me", "replace-me"}


def credentials_are_placeholders() -> bool:
    values = (
        settings.shopify_client_id or "",
        settings.shopify_client_secret.get_secret_value() if settings.shopify_client_secret else "",
    )
    return any(
        value.strip().casefold() in PLACEHOLDER_CREDENTIALS
        or value.strip().casefold().startswith("your-")
        for value in values
    )


def to_api_error(exc: ShopifyAPIError) -> HTTPException:
    if exc.reason_code == "shop_not_permitted":
        return HTTPException(
            status_code=403,
            detail=(
                "Shopify does not allow these app credentials to access this store. "
                "The app and store must belong to the same Shopify organization. "
                "Check that both appear under the same organization in Shopify Dev Dashboard."
            ),
        )
    if exc.reason_code in {"invalid_client", "invalid_client_id", "invalid_client_secret"}:
        return HTTPException(
            status_code=403,
            detail="Shopify rejected the app credentials. Verify the Client ID and Client Secret in Shopify Dev Dashboard.",
        )
    messages = {
        "shopify_unavailable": "Shopify is temporarily unavailable. Try again shortly.",
        "shopify_authorization_failed": "Shopify authorization could not be completed.",
        "shopify_scope_or_data_access_required": (
            "Shopify denied this order-data request. Check that the connected app has effective order-read access "
            "(write_orders includes read access), the store has granted the current app permissions, and the order "
            "is within the accessible order-history window."
        ),
        "shopify_access_denied": (
            "Shopify denied this request. Review the Shopify API diagnostic event for its access-denied code and field path."
        ),
        "shopify_required_scopes_missing": "The current Shopify access token is missing required app scopes.",
        "shopify_product_scope_missing": "The current Shopify access token does not include read_products.",
        "shopify_graphql_error": "Shopify returned a GraphQL validation or execution error. Review its safe diagnostic details in the API logs.",
        "shopify_rate_limited": "Shopify rate-limited this request. Retry after the provider backoff.",
        "shopify_credentials_unavailable": "Shopify credentials are unavailable. Check the server encryption configuration.",
        "shopify_reauthorization_required": "The Shopify connection needs to be reconnected.",
        "shopify_request_rejected": "Shopify rejected the read request.",
    }
    return HTTPException(
        status_code=exc.status_code,
        detail=messages.get(exc.code, "Shopify returned an invalid response."),
    )


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


def oauth_is_configured() -> bool:
    if (
        not (
            settings.shopify_client_id
            and settings.shopify_client_secret
            and settings.shopify_redirect_uri
            and settings.shopify_encryption_key
        )
        or credentials_are_placeholders()
    ):
        return False
    redirect = urlsplit(settings.shopify_redirect_uri)
    return (
        redirect.scheme == "https"
        and bool(redirect.hostname)
        and not any((redirect.username, redirect.password, redirect.query, redirect.fragment))
    )


def client_credentials_is_available() -> bool:
    if (
        settings.app_env != "development"
        or not settings.shopify_store_domain
        or not settings.shopify_client_id
        or settings.shopify_client_secret is None
        or settings.shopify_encryption_key is None
    ):
        return False
    if credentials_are_placeholders():
        return False
    try:
        normalize_shop_domain(settings.shopify_store_domain)
        encrypt_credential("configuration-check")
    except (RuntimeError, ValueError):
        return False
    return True


def shopify_callback_return_url(result: str) -> str:
    if not settings.shopify_redirect_uri:
        raise HTTPException(status_code=503, detail="Shopify integration is not configured")
    callback = urlsplit(settings.shopify_redirect_uri)
    return f"{callback.scheme}://{callback.netloc}/dashboard/settings?shopify={quote(result)}"


def shopify_search_value(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def shopify_query_fingerprint(shop_domain: str, customer_email: str, order_number: str) -> str:
    query = f"{shop_domain}\0{customer_email.strip().casefold()}\0{order_number.strip().casefold()}"
    return hmac.new(settings.jwt_secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def map_order(order: dict) -> ShopifyOrderOut:
    price = (order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
    tracking = []
    for fulfillment in order.get("fulfillments") or []:
        if not isinstance(fulfillment, dict):
            continue
        for info in fulfillment.get("trackingInfo") or []:
            if isinstance(info, dict):
                tracking.append(
                    ShopifyTrackingOut(
                        company=info.get("company"), number=info.get("number"), url=info.get("url")
                    )
                )
    return ShopifyOrderOut(
        id=str(order.get("id", "")),
        order_number=str(order.get("name", "")),
        created_at=order["createdAt"],
        financial_status=order.get("displayFinancialStatus"),
        fulfillment_status=order.get("displayFulfillmentStatus"),
        total_amount=str(price.get("amount", "")),
        currency=str(price.get("currencyCode", "")),
        tracking=tracking,
        cancelled_at=order.get("cancelledAt"),
        closed=order.get("closed"),
        return_status=order.get("returnStatus"),
    )


def map_order_summary(order: dict) -> ShopifyOrderSummaryOut:
    price = (order.get("currentTotalPriceSet") or {}).get("shopMoney") or {}
    return ShopifyOrderSummaryOut(
        id=str(order.get("id", "")),
        order_number=str(order.get("name", "")),
        created_at=order["createdAt"],
        financial_status=order.get("displayFinancialStatus"),
        fulfillment_status=order.get("displayFulfillmentStatus"),
        total_amount=str(price.get("amount", "")),
        currency=str(price.get("currencyCode", "")),
    )


async def installation_for(db: AsyncSession, organization_id: UUID) -> ShopifyInstallation:
    installation = await db.scalar(
        select(ShopifyInstallation)
        .where(ShopifyInstallation.organization_id == organization_id)
        .with_for_update()
    )
    if (
        installation is None
        or installation.disconnected_at is not None
        or installation.access_token_encrypted is None
        or (installation.auth_mode == "oauth" and installation.refresh_token_encrypted is None)
    ):
        raise HTTPException(status_code=409, detail="Connect a Shopify store first")
    return installation


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
    client_id, client_secret = require_oauth_configuration()
    if not validate_callback_timestamp(timestamp):
        log_shopify_event(
            "oauth_callback_rejected",
            organization_id=str(user.organization_id),
            reason="timestamp_invalid_or_expired",
        )
        raise HTTPException(status_code=403, detail="Shopify authorization callback expired")
    query_items = request.query_params.multi_items()
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
    return RedirectResponse(shopify_callback_return_url("connected"), status_code=303)


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


async def verified_lookup(
    *,
    db: AsyncSession,
    user: User,
    customer_email: str,
    order_number: str,
    limit: int,
    cursor: str | None,
) -> ShopifyOrderLookupOut:
    installation = await installation_for(db, user.organization_id)
    normalized_email = customer_email.strip().lower()
    normalized_order = order_number.strip()
    fingerprint = shopify_query_fingerprint(
        installation.shop_domain, normalized_email, normalized_order
    )
    audit = ShopifyAccessAudit(
        organization_id=user.organization_id,
        user_id=user.id,
        resource_type="orders",
        result_count=0,
        query_fingerprint=fingerprint,
        details={"shop_domain": installation.shop_domain, "verification": "pending"},
    )
    db.add(audit)

    async def persist_audit() -> None:
        await db.commit()
        await set_tenant_context(db, user.organization_id)

    if not ORDER_NUMBER.fullmatch(normalized_order):
        audit.details = {
            "shop_domain": installation.shop_domain,
            "verification": "invalid_order_number",
        }
        await persist_audit()
        raise HTTPException(status_code=422, detail="Enter a valid Shopify order number")

    try:
        access_token = await valid_access_token(db, installation)
    except ShopifyAPIError as exc:
        audit.details = {
            "shop_domain": installation.shop_domain,
            "verification": "credential_error",
        }
        await persist_audit()
        raise to_api_error(exc) from exc
    except RuntimeError as exc:
        audit.details = {
            "shop_domain": installation.shop_domain,
            "verification": "credential_error",
        }
        await persist_audit()
        raise HTTPException(
            status_code=503, detail="Shopify credentials cannot be accessed"
        ) from exc
    except HTTPException:
        audit.details = {
            "shop_domain": installation.shop_domain,
            "verification": "credential_error",
        }
        await persist_audit()
        raise

    if not normalized_order.startswith("#"):
        normalized_order = f"#{normalized_order}"
    try:
        matched = await lookup_authorized_order(
            shop_domain=installation.shop_domain,
            access_token=access_token,
            order_number=normalized_order,
            customer_email=normalized_email,
        )
        if matched is None:
            audit.details = {
                "shop_domain": installation.shop_domain,
                "verification": "not_verified",
            }
            await persist_audit()
            raise HTTPException(
                status_code=404, detail="No order matched both the order number and customer email"
            )
        history = await fetch_orders(
            installation.shop_domain,
            access_token,
            search_query=f"email:{shopify_search_value(normalized_email)}",
            limit=limit,
            cursor=cursor,
        )
    except ShopifyAPIError as exc:
        audit.details = {"shop_domain": installation.shop_domain, "verification": "provider_error"}
        if exc.code == "shopify_reauthorization_required":
            installation.disconnected_at = datetime.now(UTC)
            installation.access_token_encrypted = None
            installation.refresh_token_encrypted = None
        await persist_audit()
        raise to_api_error(exc) from exc

    matching_history = [
        item
        for item in history["nodes"]
        if isinstance(item, dict)
        and isinstance(item.get("customer"), dict)
        and isinstance(item["customer"].get("email"), str)
        and item["customer"]["email"].casefold() == normalized_email.casefold()
    ]
    customer = matched.get("customer") or {}
    if (
        not isinstance(customer, dict)
        or customer.get("email", "").casefold() != normalized_email.casefold()
    ):
        audit.details = {"shop_domain": installation.shop_domain, "verification": "not_verified"}
        await persist_audit()
        raise HTTPException(
            status_code=404, detail="No order matched both the order number and customer email"
        )
    audit.result_count = len(matching_history) + 1
    audit.details = {
        "shop_domain": installation.shop_domain,
        "verification": "order_number_and_email",
    }
    return ShopifyOrderLookupOut(
        customer=ShopifyCustomerOut(
            display_name=customer.get("displayName"),
            email=normalized_email,
            verified_by="order_number_and_email",
        ),
        matched_order=map_order(matched),
        recent_orders=[map_order(item) for item in matching_history],
        has_next_page=bool(history["page_info"].get("hasNextPage")),
        next_cursor=history["page_info"].get("endCursor"),
    )


@router.get("/orders/list", response_model=ShopifyOrderPageOut)
async def list_shopify_orders(
    limit: int = Query(default=25, ge=1, le=50),
    cursor: str | None = Query(default=None, max_length=512),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent", "viewer")),
) -> ShopifyOrderPageOut:
    """List a tenant's connected store orders without returning customer PII."""
    installation = await installation_for(db, user.organization_id)
    try:
        access_token = await valid_access_token(db, installation)
        page = await fetch_order_page(
            installation.shop_domain,
            access_token,
            limit=limit,
            cursor=cursor,
        )
    except ShopifyAPIError as exc:
        effective_scopes = effective_shopify_scopes(installation.granted_scopes)
        log_shopify_api_event(
            "orders_list_failed",
            level=logging.ERROR,
            organization_id=str(user.organization_id),
            user_id=str(user.id),
            shop_domain=installation.shop_domain,
            operation="SupportPilotOrderPage",
            error_code=exc.code,
            provider_error_code=exc.reason_code,
            provider_status_code=exc.status_code,
            granted_scopes=sorted(installation.granted_scopes),
            effective_scopes=sorted(effective_scopes),
            missing_required_scopes=sorted(set(REQUIRED_SCOPES) - effective_scopes),
        )
        raise to_api_error(exc) from exc
    except RuntimeError as exc:
        log_shopify_api_event(
            "orders_list_failed",
            level=logging.ERROR,
            organization_id=str(user.organization_id),
            user_id=str(user.id),
            shop_domain=installation.shop_domain,
            operation="SupportPilotOrderPage",
            error_code="shopify_credentials_unavailable",
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=503, detail="Shopify credentials cannot be accessed"
        ) from exc

    items = [map_order_summary(item) for item in page["nodes"] if isinstance(item, dict)]
    cursor_fingerprint = cursor or "first-page"
    db.add(
        ShopifyAccessAudit(
            organization_id=user.organization_id,
            user_id=user.id,
            resource_type="orders_list",
            result_count=len(items),
            query_fingerprint=shopify_query_fingerprint(
                installation.shop_domain,
                f"user:{user.id}",
                cursor_fingerprint,
            ),
            details={"shop_domain": installation.shop_domain, "view": "orders_list"},
        )
    )
    await db.commit()
    await set_tenant_context(db, user.organization_id)
    log_shopify_api_event(
        "orders_list_succeeded",
        organization_id=str(user.organization_id),
        user_id=str(user.id),
        shop_domain=installation.shop_domain,
        operation="SupportPilotOrderPage",
        returned_count=len(items),
        has_next_page=bool(page["page_info"].get("hasNextPage")),
    )
    page_info = page["page_info"]
    return ShopifyOrderPageOut(
        items=items,
        has_next_page=bool(page_info.get("hasNextPage")),
        next_cursor=page_info.get("endCursor"),
    )


@router.get("/orders", response_model=ShopifyOrderLookupOut)
async def lookup_shopify_orders(
    customer_email: EmailStr,
    order_number: str = Query(min_length=1, max_length=60, pattern=r"^#?[A-Za-z0-9-]+$"),
    limit: int = Query(default=10, ge=1, le=20),
    cursor: str | None = Query(default=None, max_length=512),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> ShopifyOrderLookupOut:
    # Shopify data is returned only after exact order-number AND customer-email verification.
    return await verified_lookup(
        db=db,
        user=user,
        customer_email=str(customer_email),
        order_number=order_number,
        limit=limit,
        cursor=cursor,
    )


@router.get("/orders/{order_number}", response_model=ShopifyOrderOut)
async def get_verified_shopify_order(
    order_number: str,
    customer_email: EmailStr,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> ShopifyOrderOut:
    result = await verified_lookup(
        db=db,
        user=user,
        customer_email=str(customer_email),
        order_number=order_number,
        limit=1,
        cursor=None,
    )
    return result.matched_order
