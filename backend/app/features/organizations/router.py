"""Tenant-scoped organization profile endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import Organization, User
from app.schemas.auth import OrganizationOut, OrganizationUpdate
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(tags=["team"], responses=COMMON_ERROR_RESPONSES)


@router.get("/organization", response_model=OrganizationOut)
async def get_organization(user: User = Depends(get_current_user)) -> OrganizationOut:
    organization = user.organization
    return OrganizationOut(id=organization.id, name=organization.name, slug=organization.slug)


@router.patch("/organization", response_model=OrganizationOut)
async def update_organization(
    data: OrganizationUpdate,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
) -> OrganizationOut:
    organization = await db.get(Organization, actor.organization_id)
    organization.name = data.name.strip()
    await db.flush()
    return OrganizationOut(id=organization.id, name=organization.name, slug=organization.slug)
