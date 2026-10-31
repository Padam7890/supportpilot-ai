from datetime import UTC, datetime
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_platform_owner, limit_auth_attempts
from app.core.config import settings
from app.core.security import (
    create_platform_access_token,
    create_platform_refresh_token,
    decode_platform_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.session import get_db, set_tenant_context
from app.models import Organization, PlatformOwner, PlatformRefreshSession, User
from app.schemas.auth import (
    PlatformLoginRequest,
    PlatformOwnerOut,
    PlatformTenantOut,
    PlatformTenantPage,
    PlatformTokenOut,
    RefreshRequest,
)

router = APIRouter(prefix="/platform", tags=["platform administration"])


async def issue_platform_tokens(db: AsyncSession, owner: PlatformOwner) -> PlatformTokenOut:
    access_token = create_platform_access_token(str(owner.id))
    refresh_token, expires_at = create_platform_refresh_token(str(owner.id))
    db.add(
        PlatformRefreshSession(
            platform_owner_id=owner.id,
            token_hash=hash_token(refresh_token),
            expires_at=expires_at,
        )
    )
    await db.flush()
    return PlatformTokenOut(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        platform_owner=PlatformOwnerOut.model_validate(owner),
    )


@router.post("/auth/login", response_model=PlatformTokenOut)
async def platform_login(
    data: PlatformLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> PlatformTokenOut:
    email = str(data.email).lower()
    await limit_auth_attempts(request, email, limit=10, window_seconds=900)
    owner = await db.scalar(
        select(PlatformOwner).where(PlatformOwner.email == email, PlatformOwner.is_active.is_(True))
    )
    if owner is None or not verify_password(data.password, owner.password_hash):
        raise HTTPException(status_code=401, detail="Invalid platform credentials")
    return await issue_platform_tokens(db, owner)


@router.post("/auth/refresh", response_model=PlatformTokenOut)
async def platform_refresh(
    data: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> PlatformTokenOut:
    try:
        claims = decode_platform_refresh_token(data.refresh_token)
        owner_id = UUID(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired platform refresh token") from None
    token_hash = hash_token(data.refresh_token)
    current = await db.scalar(
        select(PlatformRefreshSession)
        .where(
            PlatformRefreshSession.platform_owner_id == owner_id,
            PlatformRefreshSession.token_hash == token_hash,
        )
        .with_for_update()
    )
    now = datetime.now(UTC)
    if current is None or current.expires_at <= now:
        raise HTTPException(status_code=401, detail="Invalid or expired platform refresh token")
    if current.revoked_at is not None:
        await db.execute(
            update(PlatformRefreshSession)
            .where(
                PlatformRefreshSession.platform_owner_id == owner_id,
                PlatformRefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Platform refresh token reuse detected")
    owner = await db.get(PlatformOwner, owner_id)
    if owner is None or not owner.is_active:
        current.revoked_at = now
        raise HTTPException(status_code=401, detail="Platform account is unavailable")
    current.revoked_at = now
    return await issue_platform_tokens(db, owner)


@router.post("/auth/logout", status_code=204)
async def platform_logout(data: RefreshRequest, db: AsyncSession = Depends(get_db)) -> None:
    try:
        claims = decode_platform_refresh_token(data.refresh_token)
        owner_id = UUID(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid platform refresh token") from None
    session = await db.scalar(
        select(PlatformRefreshSession).where(
            PlatformRefreshSession.platform_owner_id == owner_id,
            PlatformRefreshSession.token_hash == hash_token(data.refresh_token),
            PlatformRefreshSession.revoked_at.is_(None),
        )
    )
    if session is not None:
        session.revoked_at = datetime.now(UTC)


@router.get("/auth/me", response_model=PlatformOwnerOut)
async def platform_me(
    owner: PlatformOwner = Depends(get_current_platform_owner),
) -> PlatformOwner:
    return owner


@router.get("/tenants", response_model=PlatformTenantPage)
async def list_tenants(
    approval_status: str | None = Query(default="pending", pattern="^(pending|approved|rejected)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _owner: PlatformOwner = Depends(get_current_platform_owner),
) -> PlatformTenantPage:
    query = select(Organization)
    count_query = select(func.count()).select_from(Organization)
    if approval_status:
        query = query.where(Organization.approval_status == approval_status)
        count_query = count_query.where(Organization.approval_status == approval_status)
    total = await db.scalar(count_query) or 0
    result = await db.execute(
        query.order_by(Organization.created_at.desc()).limit(limit).offset(offset)
    )
    return PlatformTenantPage(
        items=[PlatformTenantOut.model_validate(tenant) for tenant in result.scalars()],
        total=total,
        limit=limit,
        offset=offset,
    )


async def review_tenant(
    tenant_id: UUID,
    owner: PlatformOwner,
    db: AsyncSession,
    status: str,
) -> PlatformTenantOut:
    tenant = await db.scalar(
        select(Organization).where(Organization.id == tenant_id).with_for_update()
    )
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant request not found")
    if tenant.approval_status not in {"pending", "rejected"}:
        raise HTTPException(status_code=409, detail="Tenant request has already been approved")
    if status == "pending" and tenant.approval_status != "rejected":
        raise HTTPException(status_code=409, detail="Only rejected tenant requests can be reopened")
    if status in {"approved", "rejected"} and tenant.approval_status != "pending":
        raise HTTPException(status_code=409, detail="Only pending tenant requests can be reviewed")

    tenant.approval_status = status
    if status != "pending":
        tenant.reviewed_by_platform_owner_id = owner.id
        tenant.reviewed_at = datetime.now(UTC)
        if status == "approved":
            await set_tenant_context(db, tenant.id)
            await db.execute(
                update(User)
                .where(User.organization_id == tenant.id, User.role == "owner")
                .values(is_active=True)
            )
    return PlatformTenantOut.model_validate(tenant)


@router.post("/tenants/{tenant_id}/approve", response_model=PlatformTenantOut)
async def approve_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    owner: PlatformOwner = Depends(get_current_platform_owner),
) -> PlatformTenantOut:
    return await review_tenant(tenant_id, owner, db, "approved")


@router.post("/tenants/{tenant_id}/reject", response_model=PlatformTenantOut)
async def reject_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    owner: PlatformOwner = Depends(get_current_platform_owner),
) -> PlatformTenantOut:
    return await review_tenant(tenant_id, owner, db, "rejected")


@router.post("/tenants/{tenant_id}/reopen", response_model=PlatformTenantOut)
async def reopen_tenant(
    tenant_id: UUID,
    db: AsyncSession = Depends(get_db),
    owner: PlatformOwner = Depends(get_current_platform_owner),
) -> PlatformTenantOut:
    return await review_tenant(tenant_id, owner, db, "pending")
