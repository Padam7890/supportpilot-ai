import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=160)
    organization_slug: str = Field(
        min_length=3, max_length=80, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)


class RegistrationPendingOut(BaseModel):
    status: str = "pending_approval"
    organization_name: str
    organization_slug: str


class RegistrationStartOut(BaseModel):
    status: Literal["email_verification_required"] = "email_verification_required"
    challenge_token: str
    organization_name: str
    organization_slug: str
    expires_in: int = 600


class AuthWorkspaceOut(BaseModel):
    membership_id: uuid.UUID
    organization_name: str
    organization_slug: str


class LoginStartOut(BaseModel):
    status: Literal["workspace_selection_required", "otp_required"]
    challenge_token: str
    workspaces: list[AuthWorkspaceOut] = Field(default_factory=list)
    email_hint: str | None = None
    expires_in: int = 600


class LoginWorkspaceRequest(BaseModel):
    membership_id: uuid.UUID
    challenge_token: str = Field(min_length=32, max_length=128)


class AuthCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")
    challenge_token: str = Field(min_length=32, max_length=128)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetComplete(AuthCodeRequest):
    new_password: str = Field(min_length=12, max_length=128)


class AuthChallengeToken(BaseModel):
    challenge_token: str = Field(min_length=32, max_length=128)


class AuthFlowStatus(BaseModel):
    status: str
    message: str
    challenge_token: str | None = None
    email_hint: str | None = None
    expires_in: int | None = None


class LoginRequest(BaseModel):
    organization_slug: str | None = Field(default=None, deprecated=True)
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=4096)


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionPage(BaseModel):
    items: list[SessionOut]
    total: int
    limit: int
    offset: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: str
    is_active: bool = True


class OrganizationOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class CurrentUserOut(UserOut):
    organization: OrganizationOut


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    user: UserOut


class PlatformLoginRequest(BaseModel):
    email: EmailStr
    password: str


class PlatformOwnerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: EmailStr


class PlatformTokenOut(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "bearer"
    platform_owner: PlatformOwnerOut


class PlatformTenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    slug: str
    approval_status: str
    created_at: datetime
    reviewed_at: datetime | None
    reviewed_by_platform_owner_id: uuid.UUID | None
    requester_name: str | None = None
    requester_email: EmailStr | None = None


class PlatformTenantPage(BaseModel):
    items: list[PlatformTenantOut]
    total: int
    limit: int
    offset: int


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = Field(pattern=r"^(admin|agent|viewer)$")


class InviteCreated(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: str
    invite_token: str
    expires_at: datetime


class InvitePreview(BaseModel):
    email: EmailStr
    organization_name: str
    role: str
    expires_at: datetime


class InviteAccept(BaseModel):
    invite_token: str
    full_name: str = Field(min_length=2, max_length=160)
    password: str = Field(min_length=12, max_length=128)


class InviteOut(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class MemberUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(admin|agent|viewer)$")
    is_active: bool | None = None


class OrganizationUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
