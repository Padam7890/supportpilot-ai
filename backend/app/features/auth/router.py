from datetime import UTC, datetime
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select, update
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
from app.db.session import (
    get_db,
    set_auth_challenge_context,
    set_auth_email_context,
    set_auth_identity_context,
    set_tenant_context,
)
from app.features.ai.application.defaults import create_workspace_ai_defaults
from app.features.auth.dev_bypass import auth_dev_otp_bypass_allowed
from app.features.auth.challenges import (
    CHALLENGE_TTL,
    OTP_MAX_ATTEMPTS,
    OTP_MAX_SENDS,
    OTP_RESEND_INTERVAL,
    code_is_valid,
    create_challenge,
    email_hint,
    get_challenge,
    normalize_email,
    send_challenge_code,
)
from app.models import (
    AuthChallenge,
    AuthIdentity,
    AuthIdentityMembership,
    Organization,
    RefreshSession,
    User,
)
from app.schemas.auth import (
    AuthChallengeToken,
    AuthCodeRequest,
    AuthFlowStatus,
    AuthWorkspaceOut,
    CurrentUserOut,
    LoginRequest,
    LoginStartOut,
    LoginWorkspaceRequest,
    OrganizationOut,
    PasswordResetComplete,
    PasswordResetRequest,
    RefreshRequest,
    RegisterRequest,
    RegistrationPendingOut,
    RegistrationStartOut,
    SessionOut,
    SessionPage,
    TokenOut,
    UserOut,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(prefix="/auth", tags=["authentication"], responses=COMMON_ERROR_RESPONSES)


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
    response_model=RegistrationStartOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def register(
    data: "RegisterRequest",
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> RegistrationStartOut:
    normalized_email = normalize_email(str(data.email))
    await limit_auth_attempts(request, normalized_email, limit=5, window_seconds=3600)
    await limit_auth_attempts(
        request, normalized_email, limit=OTP_MAX_SENDS, window_seconds=600, bucket="auth-otp-send"
    )
    organization = Organization(
        name=data.organization_name.strip(),
        slug=data.organization_slug,
        approval_status="pending",
    )
    db.add(organization)
    try:
        await db.flush()
        await set_tenant_context(db, organization.id)
        await create_workspace_ai_defaults(db, organization.id)
        user = User(
            organization_id=organization.id,
            email=normalized_email,
            full_name=data.full_name.strip(),
            password_hash=hash_password(data.password),
            role="pending_owner",
            is_active=False,
        )
        db.add(user)
        await db.flush()
        _, challenge_token, _ = await create_challenge(
            db,
            identity=None,
            email=normalized_email,
            purpose="registration",
            organization_id=organization.id,
            user_id=user.id,
        )
        return RegistrationStartOut(
            challenge_token=challenge_token,
            organization_name=organization.name,
            organization_slug=organization.slug,
            expires_in=int(CHALLENGE_TTL.total_seconds()),
        )
    except IntegrityError as exc:
        if "uq_organizations_slug" in str(exc.orig):
            raise HTTPException(
                status_code=409, detail="Organization slug is already in use"
            ) from None
        raise HTTPException(status_code=409, detail="Organization could not be created") from None


@router.post("/register/verify-email", response_model=RegistrationPendingOut)
async def verify_registration_email(
    data: AuthCodeRequest, db: AsyncSession = Depends(get_db)
) -> RegistrationPendingOut:
    challenge = await get_challenge(db, data.challenge_token, purpose="registration")
    if challenge.organization_id is None or challenge.user_id is None:
        raise HTTPException(
            status_code=400, detail="Registration verification is invalid or expired"
        )
    if not code_is_valid(challenge, data.code):
        challenge.attempt_count += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    await set_tenant_context(db, challenge.organization_id)
    user = await db.scalar(
        select(User).where(
            User.id == challenge.user_id,
            User.organization_id == challenge.organization_id,
        )
    )
    organization = await db.get(Organization, challenge.organization_id)
    if user is None or organization is None:
        raise HTTPException(status_code=400, detail="Registration is unavailable")
    normalized_email = normalize_email(user.email)
    await set_auth_email_context(db, normalized_email)
    identity = await db.scalar(
        select(AuthIdentity).where(AuthIdentity.email_normalized == normalized_email)
    )
    if identity is None:
        identity = AuthIdentity(
            email_normalized=normalized_email,
            password_hash=user.password_hash,
            password_reset_required=False,
        )
        db.add(identity)
        await db.flush()
    elif identity.password_hash is not None:
        # Keep the legacy tenant credential aligned during the rollback window.
        user.password_hash = identity.password_hash
    await set_auth_identity_context(db, identity.id)
    db.add(
        AuthIdentityMembership(
            identity_id=identity.id,
            organization_id=organization.id,
            user_id=user.id,
        )
    )
    challenge.identity_id = identity.id
    challenge.consumed_at = datetime.now(UTC)
    return RegistrationPendingOut(
        status="pending_approval",
        organization_name=organization.name,
        organization_slug=organization.slug,
    )


@router.post("/login", response_model=LoginStartOut | TokenOut)
async def login(
    data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> LoginStartOut | TokenOut:
    normalized_email = normalize_email(str(data.email))
    await limit_auth_attempts(request, normalized_email, limit=20, window_seconds=900)
    await set_auth_email_context(db, normalized_email)
    identity = await db.scalar(
        select(AuthIdentity).where(AuthIdentity.email_normalized == normalized_email)
    )
    if (
        identity is None
        or identity.password_hash is None
        or identity.password_reset_required
        or not verify_password(data.password, identity.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    await set_auth_identity_context(db, identity.id)
    statement = (
        select(User, Organization)
        .join(
            AuthIdentityMembership,
            (AuthIdentityMembership.organization_id == User.organization_id)
            & (AuthIdentityMembership.user_id == User.id),
        )
        .join(Organization, Organization.id == User.organization_id)
        .where(
            AuthIdentityMembership.identity_id == identity.id,
            User.is_active.is_(True),
            Organization.approval_status == "approved",
        )
        .order_by(Organization.name, Organization.id)
    )
    if data.organization_slug:
        statement = statement.where(Organization.slug == data.organization_slug)
    rows = (await db.execute(statement)).all()
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    selected_user, selected_organization = rows[0] if len(rows) == 1 else (None, None)
    if (
        selected_user is not None
        and selected_organization is not None
        and auth_dev_otp_bypass_allowed(normalized_email)
    ):
        await set_tenant_context(db, selected_organization.id)
        return await issue_tokens(db, selected_user)
    if selected_user is not None:
        await limit_auth_attempts(
            request,
            normalized_email,
            limit=OTP_MAX_SENDS,
            window_seconds=600,
            bucket="auth-otp-send",
        )
    _, challenge_token, _ = await create_challenge(
        db,
        identity=identity,
        email=normalized_email,
        purpose="login",
        organization_id=selected_organization.id if selected_organization else None,
        user_id=selected_user.id if selected_user else None,
        send_code=selected_user is not None,
    )
    if len(rows) == 1:
        return LoginStartOut(
            status="otp_required",
            challenge_token=challenge_token,
            email_hint=email_hint(normalized_email),
            expires_in=int(CHALLENGE_TTL.total_seconds()),
        )
    return LoginStartOut(
        status="workspace_selection_required",
        challenge_token=challenge_token,
        workspaces=[
            AuthWorkspaceOut(
                membership_id=user.id,
                organization_name=organization.name,
                organization_slug=organization.slug,
            )
            for user, organization in rows
        ],
        expires_in=int(CHALLENGE_TTL.total_seconds()),
    )


@router.post("/login/select-workspace", response_model=AuthFlowStatus | TokenOut)
async def select_login_workspace(
    data: LoginWorkspaceRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthFlowStatus | TokenOut:
    await limit_auth_attempts(request, data.challenge_token, limit=10, window_seconds=900)
    challenge = await get_challenge(db, data.challenge_token, purpose="login")
    if challenge.identity_id is None or challenge.organization_id is not None:
        raise HTTPException(status_code=400, detail="Workspace selection is invalid or expired")
    await set_auth_identity_context(db, challenge.identity_id)
    row = await db.execute(
        select(User, Organization)
        .join(
            AuthIdentityMembership,
            (AuthIdentityMembership.organization_id == User.organization_id)
            & (AuthIdentityMembership.user_id == User.id),
        )
        .join(Organization, Organization.id == User.organization_id)
        .where(
            User.id == data.membership_id,
            AuthIdentityMembership.identity_id == challenge.identity_id,
            User.is_active.is_(True),
            Organization.approval_status == "approved",
        )
    )
    selected = row.one_or_none()
    if selected is None:
        raise HTTPException(status_code=404, detail="Workspace is unavailable")
    user, organization = selected
    identity = await db.get(AuthIdentity, challenge.identity_id)
    if identity is None:
        raise HTTPException(status_code=400, detail="Sign-in challenge is invalid or expired")
    challenge.organization_id = organization.id
    challenge.user_id = user.id
    if auth_dev_otp_bypass_allowed(identity.email_normalized):
        challenge.consumed_at = datetime.now(UTC)
        await set_tenant_context(db, organization.id)
        return await issue_tokens(db, user)
    await limit_auth_attempts(
        request,
        identity.email_normalized,
        limit=OTP_MAX_SENDS,
        window_seconds=600,
        bucket="auth-otp-send",
    )
    await send_challenge_code(challenge, identity.email_normalized, "login")
    return AuthFlowStatus(
        status="otp_required",
        message="A verification code was sent to your email.",
        email_hint=email_hint(identity.email_normalized),
    )


@router.post("/login/verify-code", response_model=TokenOut)
async def verify_login_code(
    data: AuthCodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> TokenOut:
    await limit_auth_attempts(request, data.challenge_token, limit=10, window_seconds=900)
    challenge = await get_challenge(db, data.challenge_token, purpose="login")
    if challenge.organization_id is None or challenge.user_id is None:
        raise HTTPException(status_code=400, detail="Select a workspace before verifying")
    if not code_is_valid(challenge, data.code):
        challenge.attempt_count += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    await set_tenant_context(db, challenge.organization_id)
    organization = await db.get(Organization, challenge.organization_id)
    user = await db.scalar(
        select(User).where(
            User.id == challenge.user_id,
            User.organization_id == challenge.organization_id,
            User.is_active.is_(True),
        )
    )
    if organization is None or organization.approval_status != "approved" or user is None:
        raise HTTPException(status_code=401, detail="Workspace membership is unavailable")
    challenge.consumed_at = datetime.now(UTC)
    return await issue_tokens(db, user)


@router.post("/resend-code", response_model=AuthFlowStatus)
async def resend_auth_code(
    data: AuthChallengeToken,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> AuthFlowStatus:
    await limit_auth_attempts(request, data.challenge_token, limit=10, window_seconds=900)
    await set_auth_challenge_context(db, hash_token(data.challenge_token))
    challenge = await db.scalar(
        select(AuthChallenge)
        .where(AuthChallenge.token_hash == hash_token(data.challenge_token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if (
        challenge is None
        or challenge.consumed_at is not None
        or challenge.expires_at <= now
        or challenge.attempt_count >= OTP_MAX_ATTEMPTS
        or challenge.purpose not in {"login", "registration", "password_reset"}
    ):
        raise HTTPException(status_code=400, detail="Verification is invalid or expired")
    if challenge.send_count >= OTP_MAX_SENDS or (
        challenge.last_sent_at is not None and challenge.last_sent_at > now - OTP_RESEND_INTERVAL
    ):
        raise HTTPException(status_code=429, detail="Wait before requesting another code")
    if challenge.purpose == "registration":
        await set_tenant_context(db, challenge.organization_id)
        user = await db.get(User, challenge.user_id)
        if user is None:
            raise HTTPException(status_code=400, detail="Registration is unavailable")
        email = user.email
    else:
        if challenge.identity_id is None:
            raise HTTPException(status_code=400, detail="Verification is unavailable")
        await set_auth_identity_context(db, challenge.identity_id)
        identity = await db.get(AuthIdentity, challenge.identity_id)
        if identity is None:
            raise HTTPException(status_code=400, detail="Verification is unavailable")
        email = identity.email_normalized
    await limit_auth_attempts(
        request, email, limit=OTP_MAX_SENDS, window_seconds=600, bucket="auth-otp-send"
    )
    await send_challenge_code(challenge, email, challenge.purpose)
    return AuthFlowStatus(status="code_sent", message=f"A code was sent to {email_hint(email)}")


@router.post("/password-reset/request", response_model=AuthFlowStatus)
async def request_password_reset(
    data: PasswordResetRequest, request: Request, db: AsyncSession = Depends(get_db)
) -> AuthFlowStatus:
    email = normalize_email(str(data.email))
    await limit_auth_attempts(request, email, limit=5, window_seconds=900)
    await set_auth_email_context(db, email)
    identity = await db.scalar(select(AuthIdentity).where(AuthIdentity.email_normalized == email))
    challenge_token = None
    if identity is not None:
        await limit_auth_attempts(
            request, email, limit=OTP_MAX_SENDS, window_seconds=600, bucket="auth-otp-send"
        )
        _, challenge_token, _ = await create_challenge(
            db, identity=identity, email=email, purpose="password_reset"
        )
    return AuthFlowStatus(
        status="requested",
        message="If an account is eligible for password recovery, a verification code has been sent.",
        challenge_token=challenge_token,
        expires_in=int(CHALLENGE_TTL.total_seconds()) if challenge_token else None,
    )


@router.post("/password-reset/complete", response_model=AuthFlowStatus)
async def complete_password_reset(
    data: PasswordResetComplete, request: Request, db: AsyncSession = Depends(get_db)
) -> AuthFlowStatus:
    await limit_auth_attempts(request, data.challenge_token, limit=10, window_seconds=900)
    challenge = await get_challenge(db, data.challenge_token, purpose="password_reset")
    if not code_is_valid(challenge, data.code):
        challenge.attempt_count += 1
        await db.commit()
        raise HTTPException(status_code=400, detail="Verification code is invalid or expired")
    if challenge.identity_id is None:
        raise HTTPException(status_code=400, detail="Password recovery is unavailable")
    await set_auth_identity_context(db, challenge.identity_id)
    identity = await db.get(AuthIdentity, challenge.identity_id)
    if identity is None:
        raise HTTPException(status_code=400, detail="Password recovery is unavailable")
    identity.password_hash = hash_password(data.new_password)
    identity.password_reset_required = False
    memberships = await db.scalars(
        select(AuthIdentityMembership).where(AuthIdentityMembership.identity_id == identity.id)
    )
    for membership in memberships:
        await set_tenant_context(db, membership.organization_id)
        await db.execute(
            update(User)
            .where(
                User.id == membership.user_id,
                User.organization_id == membership.organization_id,
            )
            .values(password_hash=identity.password_hash)
        )
    challenge.consumed_at = datetime.now(UTC)
    return AuthFlowStatus(
        status="password_updated", message="Password updated. Sign in with your new password."
    )


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


@router.get("/sessions", response_model=SessionPage)
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionPage:
    now = datetime.now(UTC)
    predicate = (
        RefreshSession.organization_id == user.organization_id,
        RefreshSession.user_id == user.id,
        RefreshSession.revoked_at.is_(None),
        RefreshSession.expires_at > now,
    )
    total = await db.scalar(select(func.count()).select_from(RefreshSession).where(*predicate)) or 0
    rows = await db.scalars(
        select(RefreshSession)
        .where(*predicate)
        .order_by(RefreshSession.created_at.desc(), RefreshSession.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return SessionPage(
        items=[SessionOut.model_validate(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    session = await db.scalar(
        select(RefreshSession)
        .where(
            RefreshSession.id == session_id,
            RefreshSession.organization_id == user.organization_id,
            RefreshSession.user_id == user.id,
            RefreshSession.revoked_at.is_(None),
        )
        .with_for_update()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Active session not found")
    session.revoked_at = datetime.now(UTC)
