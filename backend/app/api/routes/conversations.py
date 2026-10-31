from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import User
from app.repositories.conversation import ConversationRepository
from app.repositories.ticket import TicketRepository
from app.schemas.conversation import (
    ConversationCreate,
    ConversationOut,
    InternalNoteCreate,
    MessageCreate,
    MessageOut,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.services.conversation import ConversationService

router = APIRouter(tags=["conversations"], responses=COMMON_ERROR_RESPONSES)


def service(db: AsyncSession) -> ConversationService:
    return ConversationService(ConversationRepository(db), TicketRepository(db))


@router.post(
    "/tickets/{ticket_id}/conversations",
    response_model=ConversationOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    ticket_id: UUID,
    data: ConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> ConversationOut:
    return await service(db).create(user.organization_id, ticket_id, data)


@router.get("/tickets/{ticket_id}/conversations", response_model=list[ConversationOut])
async def list_conversations(
    ticket_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ConversationOut]:
    return await service(db).list_for_ticket(user.organization_id, ticket_id)


@router.post(
    "/conversations/{conversation_id}/messages", response_model=MessageOut, status_code=201
)
async def add_message(
    conversation_id: UUID,
    data: MessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> MessageOut:
    message = await service(db).add_message(user.organization_id, user.id, conversation_id, data)
    return MessageOut.model_validate(message).model_copy(update={"sender_name": user.full_name})


@router.post(
    "/conversations/{conversation_id}/notes", response_model=MessageOut, status_code=201
)
async def add_internal_note(
    conversation_id: UUID,
    data: InternalNoteCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> MessageOut:
    note = await service(db).add_internal_note(
        user.organization_id, user.id, conversation_id, data
    )
    return MessageOut.model_validate(note).model_copy(update={"sender_name": user.full_name})


@router.get("/conversations/{conversation_id}/notes", response_model=list[MessageOut])
async def list_internal_notes(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MessageOut]:
    rows = await service(db).internal_notes(user.organization_id, conversation_id)
    return [
        MessageOut.model_validate(note).model_copy(update={"sender_name": sender_name})
        for note, sender_name in rows
    ]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[MessageOut]:
    conversation = await service(db).repo.get(user.organization_id, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    rows = await service(db).repo.list_messages(user.organization_id, conversation_id)
    return [
        MessageOut.model_validate(message).model_copy(update={"sender_name": sender_name})
        for message, sender_name in rows
    ]
