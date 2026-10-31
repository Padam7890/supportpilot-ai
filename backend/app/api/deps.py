import hashlib
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.security import decode_access_token, decode_platform_access_token
from app.db.session import get_db, set_tenant_context
from app.models import Organization, PlatformOwner, User

bearer = HTTPBearer(auto_error=False)


async def limit_auth_attempts(
    request: Request,
    identity: str,
    *,
    limit: int,
    window_seconds: int,
) -> None:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        if settings.app_env == "test":
            return
        raise HTTPException(status_code=503, detail="Authentication service is unavailable")
    ip = request.client.host if request.client else "unknown"
    identity_hash = hashlib.sha256(identity.lower().encode("utf-8")).hexdigest()[:24]
    key = f"auth-rate:{request.url.path}:{ip}:{identity_hash}"
    try:
        attempts = await redis.incr(key)
        if attempts == 1:
            await redis.expire(key, window_seconds)
    except RedisError:
        if settings.app_env == "test":
            return
        raise HTTPException(
            status_code=503, detail="Authentication service is unavailable"
        ) from None
    if attempts > limit:
        raise HTTPException(
            status_code=429, detail="Too many authentication attempts. Try again later."
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        claims = decode_access_token(credentials.credentials)
        user_id_claim = claims.get("sub")
        organization_id_claim = claims.get("org")
        if not user_id_claim or not organization_id_claim:
            raise ValueError("Missing token claims")
        user_id = UUID(user_id_claim)
        organization_id = UUID(organization_id_claim)
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired access token") from None
    await set_tenant_context(db, organization_id)
    result = await db.execute(
        select(User)
        .options(selectinload(User.organization))
        .join(Organization, Organization.id == User.organization_id)
        .where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.is_active.is_(True),
            Organization.approval_status == "approved",
        )
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive account")
    return user


async def get_current_platform_owner(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> PlatformOwner:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        claims = decode_platform_access_token(credentials.credentials)
        platform_owner_id = UUID(claims.get("sub", ""))
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired platform session") from None
    owner = await db.get(PlatformOwner, platform_owner_id)
    if owner is None or not owner.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive platform account")
    return owner


def require_roles(*roles: str):
    async def role_guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user

    return role_guard
