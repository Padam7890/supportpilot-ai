from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.features.conversations.repository import ConversationRepository
from app.features.conversations.service import ConversationService
from app.features.tickets.repository import TicketRepository
from app.models import Conversation, SupportWidget, User
from app.schemas.conversation import (
    ConversationAIModeUpdate,
    ConversationCreate,
    ConversationOut,
    InternalNoteCreate,
    MessageCreate,
    MessageOut,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(tags=["conversations"], responses=COMMON_ERROR_RESPONSES)


@router.patch("/conversations/{conversation_id}/ai-mode", response_model=ConversationOut)
async def update_conversation_ai_mode(
    conversation_id: UUID,
    data: ConversationAIModeUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> ConversationOut:
    conversation = await db.scalar(
        select(Conversation)
        .where(
            Conversation.id == conversation_id,
            Conversation.organization_id == user.organization_id,
            Conversation.channel == "shopify_widget",
        )
        .with_for_update()
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Widget conversation not found")
    if data.mode == "ai":
        widget = await db.scalar(
            select(SupportWidget).where(SupportWidget.organization_id == user.organization_id)
        )
        if widget is None or not widget.enabled or not widget.ai_enabled:
            raise HTTPException(
                status_code=409,
                detail="Enable widget AI in Settings before switching this conversation to AI mode",
            )
    conversation.ai_mode = data.mode
    await db.flush()
    return ConversationOut.model_validate(conversation)


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
