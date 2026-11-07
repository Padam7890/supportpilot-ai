from sqlalchemy import select

from app.models import Conversation, IntegrationDeliveryJob, Message, User
from app.repositories.base import TenantRepository


class ConversationRepository(TenantRepository[Conversation]):
    def __init__(self, session):
        super().__init__(Conversation, session)

    async def list_for_ticket(self, organization_id, ticket_id):
        result = await self.session.scalars(
            select(Conversation)
            .where(
                Conversation.organization_id == organization_id,
                Conversation.ticket_id == ticket_id,
            )
            .order_by(Conversation.created_at.desc(), Conversation.id.desc())
        )
        return list(result.all())

    async def add_message(self, message: Message):
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_messages(self, organization_id, conversation_id):
        result = await self.session.execute(
            select(
                Message,
                User.full_name,
                IntegrationDeliveryJob.status,
                IntegrationDeliveryJob.last_error_code,
                IntegrationDeliveryJob.correlation_id,
            )
            .outerjoin(
                User,
                (User.id == Message.sender_user_id) & (User.organization_id == organization_id),
            )
            .outerjoin(
                IntegrationDeliveryJob,
                (IntegrationDeliveryJob.organization_id == Message.organization_id)
                & (IntegrationDeliveryJob.message_id == Message.id),
            )
            .where(
                Message.organization_id == organization_id,
                Message.conversation_id == conversation_id,
                Message.sender_type != "internal_note",
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return list(result.all())

    async def list_internal_notes(self, organization_id, conversation_id):
        result = await self.session.execute(
            select(Message, User.full_name)
            .outerjoin(
                User,
                (User.id == Message.sender_user_id) & (User.organization_id == organization_id),
            )
            .where(
                Message.organization_id == organization_id,
                Message.conversation_id == conversation_id,
                Message.sender_type == "internal_note",
            )
            .order_by(Message.created_at.asc(), Message.id.asc())
        )
        return list(result.all())
