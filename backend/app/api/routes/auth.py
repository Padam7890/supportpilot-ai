from datetime import UTC, datetime
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, limit_auth_attempts
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.session import get_db, set_tenant_context
from app.models import Organization, RefreshSession, User
from app.schemas.auth import (
    CurrentUserOut,
    LoginRequest,
    OrganizationOut,
    RegistrationPendingOut,
    RefreshRequest,
    RegisterRequest,
    TokenOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["authentication"])


async def issue_tokens(db: AsyncSession, user: User) -> TokenOut:
    access_token = create_access_token(str(user.id), str(user.organization_id))
    refresh_token, expires_at = create_refresh_token(str(user.id), str(user.organization_id))
    db.add(
        RefreshSession(
            organization_id=user.organization_id,
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=expires_at,
        )
    )
    await db.flush()
    return TokenOut(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


async def claims_context(token: str, db: AsyncSession) -> tuple[dict, UUID, UUID]:
    try:
        claims = decode_refresh_token(token)
        user_id = UUID(claims["sub"])
        organization_id = UUID(claims["org"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token") from None
    await set_tenant_context(db, organization_id)
    return claims, user_id, organization_id


@router.post(
    "/register",
    response_model=RegistrationPendingOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def register(
    data: "RegisterRequest",
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await limit_auth_attempts(request, data.email, limit=5, window_seconds=3600)
    organization = Organization(
        name=data.organization_name.strip(),
        slug=data.organization_slug,
        approval_status="pending",
    )
    db.add(organization)
    try:
        await db.flush()
        await set_tenant_context(db, organization.id)
        user = User(
            organization_id=organization.id,
            email=str(data.email).lower(),
            full_name=data.full_name.strip(),
            password_hash=hash_password(data.password),
            role="owner",
            is_active=False,
        )
        db.add(user)
        await db.flush()
        return {
            "status": "pending_approval",
            "organization_name": organization.name,
            "organization_slug": organization.slug,
        }
    except IntegrityError as exc:
        if "uq_organizations_slug" in str(exc.orig):
            raise HTTPException(
                status_code=409, detail="Organization slug is already in use"
            ) from None
        raise HTTPException(status_code=409, detail="Organization could not be created") from None


@router.post("/login", response_model=TokenOut)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await limit_auth_attempts(
        request,
        f"{data.organization_slug}:{data.email}",
        limit=10,
        window_seconds=900,
    )
    org_result = await db.execute(
        select(Organization).where(Organization.slug == data.organization_slug)
    )
    organization = org_result.scalar_one_or_none()
    if organization is None:
        raise HTTPException(status_code=401, detail="Invalid organization or credentials")
    await set_tenant_context(db, organization.id)
    result = await db.execute(
        select(User).where(
            User.organization_id == organization.id,
            User.email == str(data.email).lower(),
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid organization or credentials")
    if organization.approval_status == "pending":
        raise HTTPException(status_code=403, detail="Tenant registration is pending approval")
    if organization.approval_status == "rejected":
        raise HTTPException(status_code=403, detail="Tenant registration was rejected")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid organization or credentials")
    return await issue_tokens(db, user)


@router.post("/refresh", response_model=TokenOut)
async def refresh(data: "RefreshRequest", db: AsyncSession = Depends(get_db)):
    _, user_id, organization_id = await claims_context(data.refresh_token, db)
    organization = await db.get(Organization, organization_id)
    if organization is None or organization.approval_status != "approved":
        raise HTTPException(status_code=401, detail="Tenant is unavailable")
    token_hash = hash_token(data.refresh_token)
    result = await db.execute(
        select(RefreshSession)
        .where(
            RefreshSession.organization_id == organization_id,
            RefreshSession.user_id == user_id,
            RefreshSession.token_hash == token_hash,
        )
        .with_for_update()
    )
    current_session = result.scalar_one_or_none()
    if current_session is None or current_session.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    if current_session.revoked_at is not None:
        await db.execute(
            update(RefreshSession)
            .where(
                RefreshSession.organization_id == organization_id,
                RefreshSession.user_id == user_id,
                RefreshSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await db.commit()
        raise HTTPException(status_code=401, detail="Refresh token reuse detected; sign in again")
    user_result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.organization_id == organization_id,
            User.is_active.is_(True),
        )
    )
    user = user_result.scalar_one_or_none()
    if user is None:
        current_session.revoked_at = datetime.now(UTC)
        raise HTTPException(status_code=401, detail="Account is unavailable")
    current_session.revoked_at = datetime.now(UTC)
    return await issue_tokens(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(data: "RefreshRequest", db: AsyncSession = Depends(get_db)) -> None:
    _, user_id, organization_id = await claims_context(data.refresh_token, db)
    result = await db.execute(
        select(RefreshSession).where(
            RefreshSession.organization_id == organization_id,
            RefreshSession.user_id == user_id,
            RefreshSession.token_hash == hash_token(data.refresh_token),
            RefreshSession.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if session is not None:
        session.revoked_at = datetime.now(UTC)


@router.get("/me", response_model=CurrentUserOut)
async def current_user(user: User = Depends(get_current_user)) -> CurrentUserOut:
    organization = user.organization
    return CurrentUserOut(
        id=user.id,
        organization_id=user.organization_id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        organization=OrganizationOut(
            id=organization.id, name=organization.name, slug=organization.slug
        ),
    )
