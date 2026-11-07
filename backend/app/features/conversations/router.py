import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.observability import current_correlation_id
from app.db.session import get_db
from app.features.conversations.repository import ConversationRepository
from app.features.conversations.service import ConversationService
from app.features.tickets.repository import TicketRepository
from app.models import (
    AIAgent,
    Conversation,
    IntegrationDeliveryJob,
    SupportWidget,
    TicketActivity,
    User,
)
from app.schemas.conversation import (
    ConversationAIAgentUpdate,
    ConversationAIModeUpdate,
    ConversationCreate,
    ConversationOut,
    InternalNoteCreate,
    MessageCreate,
    MessageOut,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(tags=["conversations"], responses=COMMON_ERROR_RESPONSES)
logger = logging.getLogger(__name__)


@router.patch("/conversations/{conversation_id}/ai-agent", response_model=ConversationOut)
async def update_conversation_ai_agent(
    conversation_id: UUID,
    data: ConversationAIAgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> ConversationOut:
    """Pin an active bot to this widget conversation or restore automatic routing."""
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
    previous_agent_id = conversation.ai_agent_id
    previous_override = conversation.ai_agent_override

    if data.ai_agent_id is None:
        widget = await db.scalar(
            select(SupportWidget)
            .where(SupportWidget.organization_id == user.organization_id)
            .order_by(SupportWidget.created_at.asc())
            .limit(1)
        )
        if widget is None:
            raise HTTPException(status_code=409, detail="The storefront widget is unavailable")
        conversation.ai_agent_id = widget.ai_agent_id
        conversation.ai_agent_override = False
        if previous_override or previous_agent_id != conversation.ai_agent_id:
            db.add(
                TicketActivity(
                    organization_id=user.organization_id,
                    ticket_id=conversation.ticket_id,
                    actor_user_id=user.id,
                    activity_type="updated",
                    details={
                        "ai_routing": {
                            "from_agent_id": str(previous_agent_id),
                            "from_manual_override": previous_override,
                            "to_agent_id": str(conversation.ai_agent_id),
                            "to_manual_override": False,
                        }
                    },
                )
            )
        await db.flush()
        return ConversationOut.model_validate(conversation)

    agent = await db.scalar(
        select(AIAgent).where(
            AIAgent.organization_id == user.organization_id,
            AIAgent.id == data.ai_agent_id,
            AIAgent.status == "active",
        )
    )
    if agent is None:
        raise HTTPException(
            status_code=422,
            detail="Choose an active bot in this workspace",
        )
    conversation.ai_agent_id = agent.id
    conversation.ai_agent_override = True
    if previous_agent_id != agent.id or not previous_override:
        db.add(
            TicketActivity(
                organization_id=user.organization_id,
                ticket_id=conversation.ticket_id,
                actor_user_id=user.id,
                activity_type="updated",
                details={
                    "ai_routing": {
                        "from_agent_id": str(previous_agent_id),
                        "from_manual_override": previous_override,
                        "to_agent_id": str(agent.id),
                        "to_manual_override": True,
                    }
                },
            )
        )
    await db.flush()
    return ConversationOut.model_validate(conversation)


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
    correlation_id = current_correlation_id()
    logger.info(
        "conversation_list_started",
        extra={
            "correlation_id": correlation_id,
            "organization_id": str(user.organization_id),
            "ticket_id": str(ticket_id),
        },
    )
    try:
        conversations = await service(db).list_for_ticket(user.organization_id, ticket_id)
    except Exception as exc:
        logger.exception(
            "conversation_list_failed",
            extra={
                "correlation_id": correlation_id,
                "organization_id": str(user.organization_id),
                "ticket_id": str(ticket_id),
                "error_type": type(exc).__name__,
            },
        )
        raise
    logger.info(
        "conversation_list_completed",
        extra={
            "correlation_id": correlation_id,
            "organization_id": str(user.organization_id),
            "ticket_id": str(ticket_id),
            "conversation_count": len(conversations),
        },
    )
    return conversations


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
    delivery = await db.execute(
        select(
            IntegrationDeliveryJob.status,
            IntegrationDeliveryJob.last_error_code,
            IntegrationDeliveryJob.correlation_id,
        ).where(
            IntegrationDeliveryJob.organization_id == user.organization_id,
            IntegrationDeliveryJob.message_id == message.id,
        )
    )
    delivery_status = delivery.one_or_none()
    return MessageOut.model_validate(message).model_copy(
        update={
            "sender_name": user.full_name,
            "delivery_job_status": delivery_status.status if delivery_status else None,
            "delivery_error_code": delivery_status.last_error_code if delivery_status else None,
            "delivery_correlation_id": delivery_status.correlation_id if delivery_status else None,
        }
    )


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
    correlation_id = current_correlation_id()
    logger.info(
        "conversation_message_list_started",
        extra={
            "correlation_id": correlation_id,
            "organization_id": str(user.organization_id),
            "conversation_id": str(conversation_id),
        },
    )
    try:
        conversation_service = service(db)
        conversation = await conversation_service.repo.get(user.organization_id, conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        rows = await conversation_service.repo.list_messages(user.organization_id, conversation_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            logger.exception(
                "conversation_message_list_failed",
                extra={
                    "correlation_id": correlation_id,
                    "organization_id": str(user.organization_id),
                    "conversation_id": str(conversation_id),
                    "error_type": type(exc).__name__,
                },
            )
        raise
    except Exception as exc:
        logger.exception(
            "conversation_message_list_failed",
            extra={
                "correlation_id": correlation_id,
                "organization_id": str(user.organization_id),
                "conversation_id": str(conversation_id),
                "error_type": type(exc).__name__,
            },
        )
        raise
    logger.info(
        "conversation_message_list_completed",
        extra={
            "correlation_id": correlation_id,
            "organization_id": str(user.organization_id),
            "conversation_id": str(conversation_id),
            "message_count": len(rows),
        },
    )
    return [
        MessageOut.model_validate(message).model_copy(
            update={
                "sender_name": sender_name,
                "delivery_job_status": job_status,
                "delivery_error_code": error_code,
                "delivery_correlation_id": correlation_id,
            }
        )
        for message, sender_name, job_status, error_code, correlation_id in rows
    ]
