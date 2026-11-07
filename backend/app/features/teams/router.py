from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.features.teams.service import TeamService
from app.models import User
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.schemas.team import TeamCreate, TeamMembersUpdate, TeamOut, TeamUpdate

router = APIRouter(prefix="/teams", tags=["teams"], responses=COMMON_ERROR_RESPONSES)


@router.get("", response_model=list[TeamOut])
async def list_teams(
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TeamOut]:
    if include_inactive and user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Only Owners and Admins can view inactive teams")
    return await TeamService(db).list_teams(
        user.organization_id,
        include_inactive=include_inactive,
    )


@router.post("", response_model=TeamOut, status_code=201)
async def create_team(
    data: TeamCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> TeamOut:
    return await TeamService(db).create(user.organization_id, user.id, data)


@router.patch("/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: UUID,
    data: TeamUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> TeamOut:
    return await TeamService(db).update(user.organization_id, team_id, user.id, data)


@router.put("/{team_id}/members", response_model=TeamOut)
async def update_team_members(
    team_id: UUID,
    data: TeamMembersUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> TeamOut:
    return await TeamService(db).replace_members(
        user.organization_id,
        team_id,
        user.id,
        data.member_ids,
    )


@router.get("/{team_id}", response_model=TeamOut)
async def get_team(
    team_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TeamOut:
    team = await TeamService(db).get(user.organization_id, team_id)
    if not team.is_active and user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=404, detail="Team not found")
    return team
