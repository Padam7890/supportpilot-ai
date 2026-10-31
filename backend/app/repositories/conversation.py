from sqlalchemy import select

from app.models import Conversation, Message, User
from app.repositories.base import TenantRepository


class ConversationRepository(TenantRepository[Conversation]):
    def __init__(self, session):
        super().__init__(Conversation, session)

    async def add_message(self, message: Message):
        self.session.add(message)
        await self.session.flush()
        return message

    async def list_messages(self, organization_id, conversation_id):
        result = await self.session.execute(
            select(Message, User.full_name)
            .outerjoin(
                User,
                (User.id == Message.sender_user_id) & (User.organization_id == organization_id),
            )
            .where(
                Message.organization_id == organization_id,
                Message.conversation_id == conversation_id,
            )
            .order_by(Message.created_at.asc())
        )
        return list(result.all())
