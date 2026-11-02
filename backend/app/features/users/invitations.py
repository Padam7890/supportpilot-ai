import secrets
from datetime import UTC, datetime
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import limit_auth_attempts, require_roles
from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_invitation_token,
    create_refresh_token,
    decode_invitation_token,
    hash_password,
    hash_token,
)
from app.db.session import get_db, set_tenant_context
from app.models import Organization, RefreshSession, TeamInvitation, User
from app.schemas.auth import (
    InviteAccept,
    InviteCreate,
    InviteCreated,
    InviteOut,
    InvitePreview,
    TokenOut,
    UserOut,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES

invitations_router = APIRouter(tags=["team"], responses=COMMON_ERROR_RESPONSES)

@invitations_router.post("/users/invitations", response_model=InviteCreated, status_code=201)
async def create_invitation(
    data: InviteCreate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
) -> InviteCreated:
    if data.role == "admin" and actor.role != "owner":
        raise HTTPException(status_code=403, detail="Only an owner can invite admins")
    email = str(data.email).lower()
    existing_member = await db.scalar(
        select(User.id).where(User.organization_id == actor.organization_id, User.email == email)
    )
    if existing_member:
        raise HTTPException(status_code=409, detail="A member with this email already exists")
    active_invite = await db.scalar(
        select(TeamInvitation.id).where(
            TeamInvitation.organization_id == actor.organization_id,
            TeamInvitation.email == email,
            TeamInvitation.accepted_at.is_(None),
            TeamInvitation.revoked_at.is_(None),
            TeamInvitation.expires_at > datetime.now(UTC),
        )
    )
    if active_invite:
        raise HTTPException(status_code=409, detail="An active invitation already exists")
    invitation = TeamInvitation(
        organization_id=actor.organization_id,
        invited_by_id=actor.id,
        email=email,
        role=data.role,
        token_hash=secrets.token_hex(32),
        expires_at=datetime.now(UTC),
    )
    db.add(invitation)
    await db.flush()
    token, expires_at = create_invitation_token(str(invitation.id), str(actor.organization_id))
    invitation.token_hash = hash_token(token)
    invitation.expires_at = expires_at
    return InviteCreated(
        id=invitation.id,
        email=email,
        role=invitation.role,
        invite_token=token,
        expires_at=expires_at,
    )


@invitations_router.get("/users/invitations", response_model=list[InviteOut])
async def list_invitations(
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
) -> list[TeamInvitation]:
    result = await db.execute(
        select(TeamInvitation)
        .where(TeamInvitation.organization_id == actor.organization_id)
        .order_by(TeamInvitation.created_at.desc())
    )
    return list(result.scalars().all())


@invitations_router.delete("/users/invitations/{invitation_id}", status_code=204)
async def revoke_invitation(
    invitation_id: UUID,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
) -> None:
    invitation = await db.scalar(
        select(TeamInvitation).where(
            TeamInvitation.id == invitation_id,
            TeamInvitation.organization_id == actor.organization_id,
        )
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    if invitation.accepted_at is not None:
        raise HTTPException(status_code=409, detail="Invitation has already been accepted")
    invitation.revoked_at = datetime.now(UTC)


@invitations_router.post("/auth/invitations/accept", response_model=TokenOut, status_code=201)
async def accept_invitation(
    data: InviteAccept,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    await limit_auth_attempts(request, data.invite_token, limit=10, window_seconds=900)
    try:
        claims = decode_invitation_token(data.invite_token)
        invitation_id = UUID(claims["sub"])
        organization_id = UUID(claims["org"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail="Invitation link is invalid or expired"
        ) from None
    await set_tenant_context(db, organization_id)
    invitation = await db.scalar(
        select(TeamInvitation)
        .where(
            TeamInvitation.id == invitation_id,
            TeamInvitation.organization_id == organization_id,
        )
        .with_for_update()
    )
    now = datetime.now(UTC)
    if (
        invitation is None
        or invitation.token_hash != hash_token(data.invite_token)
        or invitation.expires_at <= now
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
    ):
        raise HTTPException(status_code=400, detail="Invitation link is invalid or expired")
    organization = await db.get(Organization, organization_id)
    if organization is None or organization.approval_status != "approved":
        raise HTTPException(status_code=403, detail="Tenant registration is not approved")
    email_exists = await db.scalar(
        select(User.id).where(
            User.organization_id == organization_id, User.email == invitation.email
        )
    )
    if email_exists:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(
        organization_id=organization_id,
        email=invitation.email,
        full_name=data.full_name.strip(),
        password_hash=hash_password(data.password),
        role=invitation.role,
    )
    db.add(user)
    invitation.accepted_at = now
    await db.flush()
    access_token = create_access_token(str(user.id), str(organization_id))
    refresh_token, refresh_expires = create_refresh_token(str(user.id), str(organization_id))
    db.add(
        RefreshSession(
            organization_id=organization_id,
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=refresh_expires,
        )
    )
    await db.flush()
    return TokenOut(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@invitations_router.get("/auth/invitations/{invite_token}", response_model=InvitePreview)
async def preview_invitation(
    invite_token: str, db: AsyncSession = Depends(get_db)
) -> InvitePreview:
    try:
        claims = decode_invitation_token(invite_token)
        invitation_id = UUID(claims["sub"])
        organization_id = UUID(claims["org"])
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Invitation not found") from None
    await set_tenant_context(db, organization_id)
    invitation = await db.scalar(
        select(TeamInvitation).where(
            TeamInvitation.id == invitation_id,
            TeamInvitation.organization_id == organization_id,
            TeamInvitation.token_hash == hash_token(invite_token),
            TeamInvitation.accepted_at.is_(None),
            TeamInvitation.revoked_at.is_(None),
            TeamInvitation.expires_at > datetime.now(UTC),
        )
    )
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found")
    organization = await db.get(Organization, organization_id)
    return InvitePreview(
        email=invitation.email,
        organization_name=organization.name,
        role=invitation.role,
        expires_at=invitation.expires_at,
    )

