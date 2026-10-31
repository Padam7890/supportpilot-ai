import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.api.routes.integrations import verified_lookup
from app.core.config import settings
from app.db.session import get_db
from app.models import AIExecution, Conversation, Customer, Message, Organization, Ticket, User
from app.schemas.ai import (
    AIExecutionOut,
    AIExecutionPage,
    AIPlaygroundRequest,
    AIReplyDraftRequest,
    WidgetAIReplyStatusOut,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.services.ai_execution import is_provider_configured
from app.services.shopify_security import encrypt_credential

router = APIRouter(prefix="/ai", tags=["AI assistance"], responses=COMMON_ERROR_RESPONSES)
MAX_ACTIVE_EXECUTIONS_PER_TENANT = 10


async def enqueue_execution(
    *,
    db: AsyncSession,
    user: User,
    kind: str,
    question: str,
    instructions: str | None = None,
    conversation_id: UUID | None = None,
    integration_context_encrypted: str | None = None,
) -> AIExecutionOut:
    if not is_provider_configured():
        raise HTTPException(
            status_code=503,
            detail="AI provider is not configured for this workspace",
        )
    # Serialize active-count checks and inserts for this tenant. Concurrent
    # requests otherwise can all observe spare capacity and exceed the limit.
    organization_id = await db.scalar(
        select(Organization.id)
        .where(Organization.id == user.organization_id)
        .with_for_update()
    )
    if organization_id is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    active = await db.scalar(
        select(func.count(AIExecution.id)).where(
            AIExecution.organization_id == user.organization_id,
            AIExecution.status.in_(["queued", "running"]),
        )
    ) or 0
    if active >= MAX_ACTIVE_EXECUTIONS_PER_TENANT:
        raise HTTPException(status_code=429, detail="Too many AI requests are already in progress")
    execution = AIExecution(
        organization_id=user.organization_id,
        requested_by_user_id=user.id,
        conversation_id=conversation_id,
        kind=kind,
        status="queued",
        question=question,
        instructions=instructions,
        integration_context_encrypted=integration_context_encrypted,
        max_attempts=settings.ai_provider_max_attempts,
    )
    db.add(execution)
    await db.flush()
    return AIExecutionOut.model_validate(execution)


@router.post("/playground", response_model=AIExecutionOut, status_code=status.HTTP_202_ACCEPTED)
async def create_playground_execution(
    data: AIPlaygroundRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> AIExecutionOut:
    return await enqueue_execution(
        db=db,
        user=user,
        kind="playground",
        question=data.question.strip(),
    )


@router.post("/reply-drafts", response_model=AIExecutionOut, status_code=status.HTTP_202_ACCEPTED)
async def create_reply_draft(
    data: AIReplyDraftRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> AIExecutionOut:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == data.conversation_id,
            Conversation.organization_id == user.organization_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    encrypted_context = None
    if data.shopify_order_number:
        ticket = await db.scalar(
            select(Ticket).where(
                Ticket.id == conversation.ticket_id,
                Ticket.organization_id == user.organization_id,
            )
        )
        customer = await db.scalar(
            select(Customer).where(
                Customer.id == ticket.customer_id,
                Customer.organization_id == user.organization_id,
            )
        ) if ticket else None
        if customer is None or not customer.email:
            raise HTTPException(status_code=409, detail="This conversation has no customer email to verify the order")
        # Verify against the CRM email tied to this conversation, never an email supplied by the caller.
        verified = await verified_lookup(
            db=db,
            user=user,
            customer_email=customer.email,
            order_number=data.shopify_order_number,
            limit=1,
            cursor=None,
        )
        order = verified.matched_order
        safe_order_facts = {
            "order_number": order.order_number,
            "created_at": order.created_at.isoformat(),
            "financial_status": order.financial_status,
            "fulfillment_status": order.fulfillment_status,
            "total_amount": order.total_amount,
            "currency": order.currency,
            "tracking": [
                {"company": tracking.company, "status": "tracking_available" if tracking.number else "pending"}
                for tracking in order.tracking
            ],
        }
        try:
            encrypted_context = encrypt_credential(json.dumps(safe_order_facts, separators=(",", ":")))
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="Shopify order context encryption is unavailable") from exc
    return await enqueue_execution(
        db=db,
        user=user,
        kind="reply_draft",
        question="Draft a response to the latest customer message in this conversation.",
        instructions=data.instructions.strip() if data.instructions else None,
        conversation_id=conversation.id,
        integration_context_encrypted=encrypted_context,
    )


@router.get("/executions", response_model=AIExecutionPage)
async def list_executions(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AIExecutionPage:
    predicate = AIExecution.organization_id == user.organization_id
    total = await db.scalar(select(func.count()).select_from(AIExecution).where(predicate)) or 0
    executions = await db.scalars(
        select(AIExecution)
        .where(predicate)
        .order_by(AIExecution.created_at.desc(), AIExecution.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return AIExecutionPage(
        items=[AIExecutionOut.model_validate(execution) for execution in executions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/executions/{execution_id}", response_model=AIExecutionOut)
async def get_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AIExecutionOut:
    execution = await db.scalar(
        select(AIExecution).where(
            AIExecution.id == execution_id,
            AIExecution.organization_id == user.organization_id,
        )
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="AI execution not found")
    return AIExecutionOut.model_validate(execution)


@router.get(
    "/conversations/{conversation_id}/widget-reply",
    response_model=WidgetAIReplyStatusOut | None,
)
async def get_widget_reply_status(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WidgetAIReplyStatusOut | None:
    conversation = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == user.organization_id,
            Conversation.channel == "shopify_widget",
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Widget conversation not found")
    if conversation.ai_mode != "ai":
        return None
    execution = await db.scalar(
        select(AIExecution)
        .where(
            AIExecution.organization_id == user.organization_id,
            AIExecution.conversation_id == conversation_id,
            AIExecution.kind == "widget_reply",
        )
        .order_by(AIExecution.created_at.desc(), AIExecution.id.desc())
        .limit(1)
    )
    if execution is None or execution.reply_status is None or execution.delivery_mode is None:
        return None
    source = None
    if execution.source_message_id:
        source = await db.scalar(
            select(Message).where(
                Message.id == execution.source_message_id,
                Message.organization_id == user.organization_id,
                Message.conversation_id == conversation_id,
            )
        )
    if source is not None:
        teammate_activity = await db.scalar(
            select(Message.id)
            .where(
                Message.organization_id == user.organization_id,
                Message.conversation_id == conversation_id,
                Message.sender_type.in_(("agent", "internal_note")),
                Message.created_at >= source.created_at,
            )
            .limit(1)
        )
        newer_customer_message = await db.scalar(
            select(Message.id)
            .where(
                Message.organization_id == user.organization_id,
                Message.conversation_id == conversation_id,
                Message.sender_type == "customer",
                (Message.created_at > source.created_at)
                | ((Message.created_at == source.created_at) & (Message.id > source.id)),
            )
            .limit(1)
        )
        if teammate_activity or newer_customer_message:
            return None
    return WidgetAIReplyStatusOut(
        status=execution.reply_status,
        delivery_mode=execution.delivery_mode,
        draft=execution.draft if execution.reply_status == "draft_ready" else None,
        safe_summary=execution.safe_summary,
        citations=execution.citations,
        updated_at=execution.updated_at,
    )
