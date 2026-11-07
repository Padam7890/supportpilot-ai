from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, Team, TeamAudit, TeamMember, Ticket, User
from app.schemas.team import TeamCreate, TeamMemberOut, TeamOut, TeamUpdate

ELIGIBLE_MEMBER_ROLES = ("owner", "admin", "agent")
ACTIVE_TICKET_STATUSES = ("open", "pending")


class TeamService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_teams(self, organization_id: UUID, *, include_inactive: bool = False) -> list[TeamOut]:
        query = select(Team).where(Team.organization_id == organization_id)
        if not include_inactive:
            query = query.where(Team.is_active.is_(True))
        teams = list((await self.db.scalars(query.order_by(Team.is_active.desc(), Team.name, Team.id))).all())
        if not teams:
            return []
        team_ids = [team.id for team in teams]
        member_rows = await self.db.execute(
            select(TeamMember.team_id, User)
            .join(
                User,
                (User.organization_id == TeamMember.organization_id)
                & (User.id == TeamMember.user_id),
            )
            .where(
                TeamMember.organization_id == organization_id,
                TeamMember.team_id.in_(team_ids),
                User.is_active.is_(True),
                User.role.in_(ELIGIBLE_MEMBER_ROLES),
            )
            .order_by(TeamMember.team_id, User.full_name, User.id)
        )
        members_by_team: dict[UUID, list[TeamMemberOut]] = {team_id: [] for team_id in team_ids}
        for team_id, member in member_rows.all():
            members_by_team[team_id].append(
                TeamMemberOut(
                    id=member.id,
                    full_name=member.full_name,
                    email=member.email,
                    role=member.role,
                )
            )
        ticket_counts = dict(
            (
                team_id,
                int(count),
            )
            for team_id, count in (
                await self.db.execute(
                    select(Ticket.team_id, func.count(Ticket.id))
                    .where(
                        Ticket.organization_id == organization_id,
                        Ticket.team_id.in_(team_ids),
                        Ticket.status.in_(ACTIVE_TICKET_STATUSES),
                    )
                    .group_by(Ticket.team_id)
                )
            ).all()
        )
        return [
            self._as_output(team, members_by_team[team.id], ticket_counts.get(team.id, 0))
            for team in teams
        ]

    async def create(self, organization_id: UUID, actor_id: UUID, data: TeamCreate) -> TeamOut:
        await self._lock_organization(organization_id)
        await self._ensure_name_available(organization_id, data.name)
        users = await self._resolve_members(organization_id, data.member_ids)
        team = Team(
            organization_id=organization_id,
            name=data.name,
            description=data.description,
            is_active=True,
        )
        self.db.add(team)
        await self.db.flush()
        self.db.add_all(
            TeamMember(organization_id=organization_id, team_id=team.id, user_id=member.id)
            for member in users
        )
        self.db.add(
            TeamAudit(
                organization_id=organization_id,
                team_id=team.id,
                actor_user_id=actor_id,
                event_type="created",
                details={"name": team.name, "member_ids": [str(member.id) for member in users]},
            )
        )
        await self.db.flush()
        return await self.get(organization_id, team.id)

    async def update(
        self, organization_id: UUID, team_id: UUID, actor_id: UUID, data: TeamUpdate
    ) -> TeamOut:
        team = await self._get_locked(organization_id, team_id)
        changes = data.model_dump(exclude_unset=True)
        if "name" in changes and changes["name"] != team.name:
            await self._lock_organization(organization_id)
            await self._ensure_name_available(organization_id, changes["name"], excluding=team_id)
        before = {key: getattr(team, key) for key in changes}
        for key, value in changes.items():
            setattr(team, key, value)
        self.db.add(
            TeamAudit(
                organization_id=organization_id,
                team_id=team.id,
                actor_user_id=actor_id,
                event_type="updated",
                details={"before": before, "after": changes},
            )
        )
        await self.db.flush()
        return await self.get(organization_id, team_id)

    async def replace_members(
        self, organization_id: UUID, team_id: UUID, actor_id: UUID, member_ids: list[UUID]
    ) -> TeamOut:
        team = await self._get_locked(organization_id, team_id)
        if not team.is_active:
            raise HTTPException(status_code=409, detail="Reactivate this team before changing its members")
        users = await self._resolve_members(organization_id, member_ids)
        current_ids = set(
            await self.db.scalars(
                select(TeamMember.user_id)
                .where(
                    TeamMember.organization_id == organization_id,
                    TeamMember.team_id == team_id,
                )
                .order_by(TeamMember.user_id)
                .with_for_update()
            )
        )
        requested_ids = {member.id for member in users}
        if current_ids != requested_ids:
            await self.db.execute(
                delete(TeamMember).where(
                    TeamMember.organization_id == organization_id,
                    TeamMember.team_id == team_id,
                    TeamMember.user_id.in_(current_ids - requested_ids),
                )
            )
            self.db.add_all(
                TeamMember(organization_id=organization_id, team_id=team_id, user_id=user_id)
                for user_id in sorted(requested_ids - current_ids, key=str)
            )
            self.db.add(
                TeamAudit(
                    organization_id=organization_id,
                    team_id=team_id,
                    actor_user_id=actor_id,
                    event_type="members_updated",
                    details={
                        "added_user_ids": [str(user_id) for user_id in sorted(requested_ids - current_ids, key=str)],
                        "removed_user_ids": [str(user_id) for user_id in sorted(current_ids - requested_ids, key=str)],
                    },
                )
            )
        await self.db.flush()
        return await self.get(organization_id, team_id)

    async def get(self, organization_id: UUID, team_id: UUID) -> TeamOut:
        team = await self.db.scalar(
            select(Team).where(Team.organization_id == organization_id, Team.id == team_id)
        )
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")
        member_rows = await self.db.execute(
            select(User)
            .join(
                TeamMember,
                (TeamMember.organization_id == User.organization_id)
                & (TeamMember.user_id == User.id),
            )
            .where(
                TeamMember.organization_id == organization_id,
                TeamMember.team_id == team_id,
                User.is_active.is_(True),
                User.role.in_(ELIGIBLE_MEMBER_ROLES),
            )
            .order_by(User.full_name, User.id)
        )
        members = [
            TeamMemberOut(id=user.id, full_name=user.full_name, email=user.email, role=user.role)
            for user in member_rows.scalars()
        ]
        active_ticket_count = int(
            await self.db.scalar(
                select(func.count(Ticket.id)).where(
                    Ticket.organization_id == organization_id,
                    Ticket.team_id == team_id,
                    Ticket.status.in_(ACTIVE_TICKET_STATUSES),
                )
            )
            or 0
        )
        return self._as_output(team, members, active_ticket_count)

    @staticmethod
    def _as_output(team: Team, members: list[TeamMemberOut], active_ticket_count: int) -> TeamOut:
        return TeamOut(
            id=team.id,
            organization_id=team.organization_id,
            name=team.name,
            description=team.description,
            is_active=team.is_active,
            members=members,
            active_ticket_count=active_ticket_count,
            created_at=team.created_at,
            updated_at=team.updated_at,
        )

    async def _get_locked(self, organization_id: UUID, team_id: UUID) -> Team:
        team = await self.db.scalar(
            select(Team)
            .where(Team.organization_id == organization_id, Team.id == team_id)
            .with_for_update()
        )
        if team is None:
            raise HTTPException(status_code=404, detail="Team not found")
        return team

    async def _lock_organization(self, organization_id: UUID) -> None:
        organization = await self.db.scalar(
            select(Organization).where(Organization.id == organization_id).with_for_update()
        )
        if organization is None:
            raise HTTPException(status_code=404, detail="Workspace not found")

    async def _ensure_name_available(
        self, organization_id: UUID, name: str, *, excluding: UUID | None = None
    ) -> None:
        query = select(Team.id).where(
            Team.organization_id == organization_id,
            func.lower(Team.name) == name.casefold(),
        )
        if excluding is not None:
            query = query.where(Team.id != excluding)
        if await self.db.scalar(query):
            raise HTTPException(status_code=409, detail="A team with this name already exists")

    async def _resolve_members(self, organization_id: UUID, member_ids: list[UUID]) -> list[User]:
        if not member_ids:
            return []
        users = list(
            await self.db.scalars(
                select(User)
                .where(
                    User.organization_id == organization_id,
                    User.id.in_(member_ids),
                    User.is_active.is_(True),
                    User.role.in_(ELIGIBLE_MEMBER_ROLES),
                )
                .order_by(User.id)
                .with_for_update()
            )
        )
        if {user.id for user in users} != set(member_ids):
            raise HTTPException(
                status_code=422,
                detail="Every team member must be an active Owner, Admin, or Agent in this workspace",
            )
        return users
