"""Application services for tenant-scoped Shopify credentials and access tokens."""

import logging
from datetime import timedelta
from urllib.parse import quote, urlsplit
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.integrations.providers.shopify.security import (
    encrypt_credential,
    normalize_shop_domain,
)
from app.models import ShopifyInstallation

logger = logging.getLogger(__name__)
TOKEN_REFRESH_SKEW = timedelta(minutes=5)
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
