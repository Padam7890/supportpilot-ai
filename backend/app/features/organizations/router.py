"""Tenant-scoped organization profile endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import Organization, User
from app.schemas.auth import FirstResponseSlaPolicy, OrganizationOut, OrganizationUpdate
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(tags=["team"], responses=COMMON_ERROR_RESPONSES)


@router.get("/organization/sla", response_model=FirstResponseSlaPolicy)
async def get_first_response_sla(user: User = Depends(get_current_user)) -> FirstResponseSlaPolicy:
    """Read the workspace first-response targets in elapsed minutes."""
    return FirstResponseSlaPolicy.model_validate(user.organization.first_response_sla_minutes)


@router.put("/organization/sla", response_model=FirstResponseSlaPolicy)
async def update_first_response_sla(
    data: FirstResponseSlaPolicy,
    db: AsyncSession = Depends(get_db),
    actor: User = Depends(require_roles("owner", "admin")),
) -> FirstResponseSlaPolicy:
    organization = await db.get(Organization, actor.organization_id, with_for_update=True)
    organization.first_response_sla_minutes = data.model_dump()
    await db.flush()
    return data


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
