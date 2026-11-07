from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models import Ticket, TicketActivity, TicketLink
from app.schemas.ticket import TicketLinkOut


class TicketLinkService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_for_ticket(
        self,
        organization_id: UUID,
        ticket_id: UUID,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[TicketLinkOut], int]:
        await self._require_ticket(organization_id, ticket_id)
        filters = (
            TicketLink.organization_id == organization_id,
            or_(TicketLink.ticket_low_id == ticket_id, TicketLink.ticket_high_id == ticket_id),
        )
        total = int(
            await self.db.scalar(
                select(func.count()).select_from(TicketLink).where(*filters)
            )
            or 0
        )
        linked_ticket = aliased(Ticket)
        linked_pair = and_(
            linked_ticket.organization_id == TicketLink.organization_id,
            or_(
                and_(
                    TicketLink.ticket_low_id == ticket_id,
                    linked_ticket.id == TicketLink.ticket_high_id,
                ),
                and_(
                    TicketLink.ticket_high_id == ticket_id,
                    linked_ticket.id == TicketLink.ticket_low_id,
                ),
            ),
        )
        rows = await self.db.execute(
            select(TicketLink, linked_ticket)
            .join(linked_ticket, linked_pair)
            .where(*filters)
            .order_by(TicketLink.created_at.desc(), TicketLink.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return [self._to_output(link, related) for link, related in rows.all()], total

    async def create(
        self,
        organization_id: UUID,
        ticket_id: UUID,
        related_ticket_id: UUID,
        actor_user_id: UUID,
    ) -> TicketLinkOut:
        if ticket_id == related_ticket_id:
            raise HTTPException(status_code=422, detail="A ticket cannot be linked to itself")

        locked_ids = await self.db.scalars(
            select(Ticket.id)
            .where(
                Ticket.organization_id == organization_id,
                Ticket.id.in_((ticket_id, related_ticket_id)),
            )
            .order_by(Ticket.id)
            .with_for_update()
        )
        if len(locked_ids.all()) != 2:
            raise HTTPException(status_code=404, detail="One or both tickets were not found")

        low_id, high_id = sorted((ticket_id, related_ticket_id))
        link = await self.db.scalar(
            select(TicketLink).where(
                TicketLink.organization_id == organization_id,
                TicketLink.ticket_low_id == low_id,
                TicketLink.ticket_high_id == high_id,
            )
        )
        if link is None:
            link = TicketLink(
                organization_id=organization_id,
                ticket_low_id=low_id,
                ticket_high_id=high_id,
                created_by_user_id=actor_user_id,
            )
            self.db.add(link)
            await self.db.flush()
            self.db.add_all(
                [
                    self._activity(organization_id, ticket_id, related_ticket_id, link, actor_user_id, "linked"),
                    self._activity(organization_id, related_ticket_id, ticket_id, link, actor_user_id, "linked"),
                ]
            )
            await self.db.flush()

        related = await self.db.scalar(
            select(Ticket).where(
                Ticket.organization_id == organization_id,
                Ticket.id == related_ticket_id,
            )
        )
        if related is None:
            raise HTTPException(status_code=404, detail="Related ticket not found")
        return self._to_output(link, related)

    async def remove(
        self,
        organization_id: UUID,
        ticket_id: UUID,
        link_id: UUID,
        actor_user_id: UUID,
    ) -> None:
        link_filter = (
            TicketLink.organization_id == organization_id,
            TicketLink.id == link_id,
            or_(TicketLink.ticket_low_id == ticket_id, TicketLink.ticket_high_id == ticket_id),
        )
        link_snapshot = await self.db.scalar(select(TicketLink).where(*link_filter))
        if link_snapshot is None:
            raise HTTPException(status_code=404, detail="Ticket link not found")
        locked_ticket_ids = await self.db.scalars(
            select(Ticket.id)
            .where(
                Ticket.organization_id == organization_id,
                Ticket.id.in_((link_snapshot.ticket_low_id, link_snapshot.ticket_high_id)),
            )
            .order_by(Ticket.id)
            .with_for_update()
        )
        if len(locked_ticket_ids.all()) != 2:
            raise HTTPException(status_code=404, detail="Ticket link not found")
        link = await self.db.scalar(
            select(TicketLink)
            .where(*link_filter)
            .with_for_update()
        )
        if link is None:
            raise HTTPException(status_code=404, detail="Ticket link not found")

        related_ticket_id = (
            link.ticket_high_id if link.ticket_low_id == ticket_id else link.ticket_low_id
        )
        self.db.add_all(
            [
                self._activity(organization_id, ticket_id, related_ticket_id, link, actor_user_id, "unlinked"),
                self._activity(organization_id, related_ticket_id, ticket_id, link, actor_user_id, "unlinked"),
            ]
        )
        await self.db.delete(link)
        await self.db.flush()

    async def _require_ticket(self, organization_id: UUID, ticket_id: UUID) -> None:
        exists = await self.db.scalar(
            select(Ticket.id).where(
                Ticket.organization_id == organization_id,
                Ticket.id == ticket_id,
            )
        )
        if exists is None:
            raise HTTPException(status_code=404, detail="Ticket not found")

    @staticmethod
    def _activity(
        organization_id: UUID,
        ticket_id: UUID,
        related_ticket_id: UUID,
        link: TicketLink,
        actor_user_id: UUID,
        action: str,
    ) -> TicketActivity:
        return TicketActivity(
            organization_id=organization_id,
            ticket_id=ticket_id,
            actor_user_id=actor_user_id,
            activity_type="updated",
            details={
                "ticket_link": action,
                "link_id": str(link.id),
                "related_ticket_id": str(related_ticket_id),
            },
        )

    @staticmethod
    def _to_output(link: TicketLink, related: Ticket) -> TicketLinkOut:
        return TicketLinkOut(
            id=link.id,
            related_ticket_id=related.id,
            related_ticket_subject=related.subject,
            related_ticket_status=related.status,
            related_ticket_priority=related.priority,
            created_by_user_id=link.created_by_user_id,
            created_at=link.created_at,
        )
