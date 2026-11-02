from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import Organization, User
from app.schemas.auth import (
    MemberUpdate,
    UserOut,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(tags=["team"], responses=COMMON_ERROR_RESPONSES)


@router.get("/users", response_model=list[UserOut])
async def list_members(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[User]:
    result = await db.execute(
        select(User)
        .where(User.organization_id == user.organization_id)
        .order_by(User.full_name, User.email)
    )
    return list(result.scalars().all())


@router.patch("/users/{member_id}", response_model=UserOut)
async def update_member(
    member_id: UUID,
    data: MemberUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
) -> User:
    if member_id == actor.id and data.is_active is False:
        raise HTTPException(status_code=409, detail="You cannot deactivate your own account")
    result = await db.execute(
        select(User)
        .where(User.id == member_id, User.organization_id == actor.organization_id)
        .with_for_update()
    )
    member = result.scalar_one_or_none()
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    if actor.role == "admin" and (member.role == "owner" or data.role == "admin"):
        raise HTTPException(status_code=403, detail="Only an owner can manage admin roles")
    if member.role == "owner" and (data.is_active is False or data.role is not None):
        await db.scalar(
            select(Organization).where(Organization.id == actor.organization_id).with_for_update()
        )
        active_owners = await db.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.organization_id == actor.organization_id,
                User.role == "owner",
                User.is_active.is_(True),
            )
        )
        if active_owners <= 1:
            raise HTTPException(status_code=409, detail="An organization must keep an active owner")
        if actor.role != "owner":
            raise HTTPException(status_code=403, detail="Only an owner can manage owner accounts")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(member, key, value)
    await db.flush()
    return member










