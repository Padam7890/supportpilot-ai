from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException

from app.models import Conversation, Message
from app.repositories.conversation import ConversationRepository
from app.repositories.ticket import TicketRepository
from app.schemas.conversation import ConversationCreate, MessageCreate


class ConversationService:
    def __init__(self, repo: ConversationRepository, tickets: TicketRepository):
        self.repo = repo
        self.tickets = tickets

    async def create(self, organization_id: UUID, ticket_id: UUID, data: ConversationCreate):
        if not await self.tickets.get(organization_id, ticket_id):
            raise HTTPException(status_code=404, detail="Ticket not found")
        return await self.repo.add(
            Conversation(organization_id=organization_id, ticket_id=ticket_id, channel=data.channel)
        )

    async def list_for_ticket(self, organization_id: UUID, ticket_id: UUID):
        if not await self.tickets.get(organization_id, ticket_id):
            raise HTTPException(status_code=404, detail="Ticket not found")
        from sqlalchemy import select

        result = await self.repo.session.execute(
            select(Conversation)
            .where(
                Conversation.organization_id == organization_id,
                Conversation.ticket_id == ticket_id,
            )
            .order_by(Conversation.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_message(
        self, organization_id: UUID, user_id: UUID, conversation_id: UUID, data: MessageCreate
    ):
        conversation = await self.repo.get(organization_id, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        message = Message(
            organization_id=organization_id,
            conversation_id=conversation_id,
            sender_type="agent",
            sender_user_id=user_id,
            content=data.content,
            content_type=data.content_type,
        )
        conversation.updated_at = datetime.now(UTC)
        return await self.repo.add_message(message)

    async def messages(self, organization_id: UUID, conversation_id: UUID):
        if not await self.repo.get(organization_id, conversation_id):
            raise HTTPException(status_code=404, detail="Conversation not found")
        return await self.repo.list_messages(organization_id, conversation_id)
