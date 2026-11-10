import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.core.config import settings
from app.core.observability import current_correlation_id
from app.db.session import get_db
from app.features.ai.application.conversation_verified_order_evidence import AuthorizedOrderSnapshot
from app.features.ai.application.defaults import get_default_agent
from app.features.ai.application.retrieval import build_retrieval_terms, is_contextual_follow_up
from app.features.ai.application.retrieval_search import search_agent_knowledge
from app.features.ai.infrastructure.llm_gateway import is_provider_configured
from app.integrations.providers.shopify.security import encrypt_credential
from app.models import (
    AIAgent,
    AIExecution,
    Conversation,
    Customer,
    Message,
    Organization,
    Ticket,
    User,
)
from app.schemas.ai import (
    AICitation,
    AIExecutionOut,
    AIExecutionPage,
    AIExecutionRetryOut,
    AIPlaygroundRequest,
    AIPlaygroundRetrievalPreviewOut,
    AIPlaygroundRetrievalPreviewRequest,
    AIReplyDraftRequest,
    WidgetAIReplyStatusOut,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES
from app.services.shopify_order_lookup import verified_lookup

router = APIRouter(prefix="/ai", tags=["AI assistance"], responses=COMMON_ERROR_RESPONSES)
MAX_ACTIVE_EXECUTIONS_PER_TENANT = 10
MAX_MANUAL_AI_RETRIES = 3
logger = logging.getLogger(__name__)


async def enqueue_execution(
    *,
    db: AsyncSession,
    user: User,
    kind: str,
    question: str,
    instructions: str | None = None,
    conversation_id: UUID | None = None,
    integration_context_encrypted: str | None = None,
    ai_agent_id: UUID | None = None,
    playground_history: list[dict[str, str]] | None = None,
) -> AIExecutionOut:
    if not is_provider_configured():
        raise HTTPException(
            status_code=503,
            detail="AI provider is not configured for this workspace",
        )
    # Serialize active-count checks and inserts for this tenant. Concurrent
    # requests otherwise can all observe spare capacity and exceed the limit.
    organization_id = await db.scalar(
        select(Organization.id).where(Organization.id == user.organization_id).with_for_update()
    )
    if organization_id is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    active = (
        await db.scalar(
            select(func.count(AIExecution.id)).where(
                AIExecution.organization_id == user.organization_id,
                AIExecution.status.in_(["queued", "running"]),
            )
        )
        or 0
    )
    if active >= MAX_ACTIVE_EXECUTIONS_PER_TENANT:
        raise HTTPException(status_code=429, detail="Too many AI requests are already in progress")
    selected_agent = None
    if conversation_id is not None:
        conversation_agent_id = await db.scalar(
            select(Conversation.ai_agent_id).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == user.organization_id,
            )
        )
        if conversation_agent_id is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        selected_agent = await db.scalar(
            select(AIAgent).where(
                AIAgent.id == conversation_agent_id,
                AIAgent.organization_id == user.organization_id,
            )
        )
        if selected_agent is None or selected_agent.status != "active":
            raise HTTPException(status_code=409, detail="The conversation AI agent is inactive")
    if selected_agent is None:
        if ai_agent_id is not None:
            selected_agent = await db.scalar(
                select(AIAgent).where(
                    AIAgent.id == ai_agent_id,
                    AIAgent.organization_id == user.organization_id,
                )
            )
            if selected_agent is None:
                raise HTTPException(status_code=404, detail="AI agent not found")
            if selected_agent.status != "active":
                raise HTTPException(status_code=409, detail="AI agent is inactive")
        else:
            selected_agent = await get_default_agent(db, user.organization_id)
    execution = AIExecution(
        organization_id=user.organization_id,
        requested_by_user_id=user.id,
        conversation_id=conversation_id,
        ai_agent_id=selected_agent.id,
        ai_agent_config_version=selected_agent.config_version,
        ai_agent_instructions_snapshot=selected_agent.system_instructions.strip()[:8000],
        ai_agent_tools_snapshot=list(selected_agent.allowed_tools or []),
        kind=kind,
        status="queued",
        correlation_id=current_correlation_id(),
        question=question,
        instructions=instructions,
        playground_history=playground_history if kind == "playground" else None,
        integration_context_encrypted=integration_context_encrypted,
        max_attempts=settings.ai_provider_max_attempts,
    )
    db.add(execution)
    await db.flush()
    return AIExecutionOut.model_validate(execution)


@router.post(
    "/playground/retrieval-preview",
    response_model=AIPlaygroundRetrievalPreviewOut,
)
async def preview_playground_retrieval(
    data: AIPlaygroundRetrievalPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> AIPlaygroundRetrievalPreviewOut:
    """Show which assigned passages the Playground search would retrieve, without an LLM call."""
    if data.ai_agent_id is None:
        agent = await get_default_agent(db, user.organization_id)
    else:
        agent = await db.scalar(
            select(AIAgent).where(
                AIAgent.id == data.ai_agent_id,
                AIAgent.organization_id == user.organization_id,
            )
        )
        if agent is None:
            raise HTTPException(status_code=404, detail="AI bot not found")
    if agent.status != "active":
        raise HTTPException(status_code=409, detail="AI bot is inactive")

    previous_questions = (
        [turn.content[:240] for turn in data.conversation_history if turn.role == "user"][-2:]
        if is_contextual_follow_up(data.question)
        else []
    )
    search_text = " ".join([*previous_questions, data.question])[:2000]
    result = await search_agent_knowledge(
        db,
        organization_id=user.organization_id,
        ai_agent_id=agent.id,
        search_text=search_text,
    )
    if result.matches:
        preview_status = "matched"
    elif result.active_assigned_base_count == 0:
        preview_status = "no_assigned_bases"
    elif result.ready_document_count == 0:
        preview_status = "no_ready_documents"
    elif not result.terms_available:
        preview_status = "query_too_broad"
    else:
        preview_status = "no_matches"
    return AIPlaygroundRetrievalPreviewOut(
        ai_agent_id=agent.id,
        ai_agent_name=agent.name,
        status=preview_status,
        active_assigned_base_count=result.active_assigned_base_count,
        ready_document_count=result.ready_document_count,
        matched_passage_count=len(result.matches),
        retrieval_method=result.retrieval_method,
        retrieval_latency_ms=result.retrieval_latency_ms,
        embedding_status=result.embedding_status,
        embedding_coverage=result.embedding_coverage,
        retrieval_outcome=result.retrieval_outcome,
        keyword_candidate_count=result.keyword_candidate_count,
        semantic_candidate_count=result.semantic_candidate_count,
        retrieval_terms=[term[:80] for term in build_retrieval_terms(search_text)],
        sources=[
            AICitation(
                document_id=match.document_id,
                document_name=match.document_name,
                knowledge_base_name=match.knowledge_base_name,
                chunk_index=match.chunk_index,
                excerpt=match.excerpt[:320],
                match_basis=match.match_basis,
                rrf_score=match.rrf_score,
                semantic_similarity=match.semantic_similarity,
                keyword_rank=match.keyword_rank,
                semantic_rank=match.semantic_rank,
            )
            for match in result.matches
        ],
    )


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
        ai_agent_id=data.ai_agent_id,
        playground_history=[turn.model_dump() for turn in data.conversation_history],
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
        customer = (
            await db.scalar(
                select(Customer).where(
                    Customer.id == ticket.customer_id,
                    Customer.organization_id == user.organization_id,
                )
            )
            if ticket
            else None
        )
        if customer is None or not customer.email:
            raise HTTPException(
                status_code=409,
                detail="This conversation has no customer email to verify the order",
            )
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
        try:
            encrypted_context = encrypt_credential(
                AuthorizedOrderSnapshot.from_authorized_lookup(order).model_dump_json()
            )
        except ValidationError as exc:
            raise HTTPException(
                status_code=502, detail="Shopify returned order fields that could not be verified"
            ) from exc
        except RuntimeError as exc:
            raise HTTPException(
                status_code=503, detail="Shopify order context encryption is unavailable"
            ) from exc
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


@router.post(
    "/executions/{execution_id}/retry",
    response_model=AIExecutionRetryOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_failed_execution(
    execution_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin", "agent")),
) -> AIExecutionRetryOut:
    """Requeue one safe, terminal AI failure with bounded manual attempts."""
    if not is_provider_configured():
        raise HTTPException(
            status_code=503, detail="AI provider is not configured for this workspace"
        )

    await db.scalar(
        select(Organization.id).where(Organization.id == user.organization_id).with_for_update()
    )
    execution = await db.scalar(
        select(AIExecution)
        .where(
            AIExecution.id == execution_id,
            AIExecution.organization_id == user.organization_id,
        )
        .with_for_update()
    )
    if execution is None:
        raise HTTPException(status_code=404, detail="AI execution not found")
    if execution.status != "failed":
        raise HTTPException(status_code=409, detail="Only failed AI executions can be retried")
    if execution.manual_retry_count >= MAX_MANUAL_AI_RETRIES:
        raise HTTPException(
            status_code=409, detail="This AI execution has reached its manual retry limit"
        )

    active_count = (
        await db.scalar(
            select(func.count(AIExecution.id)).where(
                AIExecution.organization_id == user.organization_id,
                AIExecution.status.in_(["queued", "running"]),
            )
        )
        or 0
    )
    if active_count >= MAX_ACTIVE_EXECUTIONS_PER_TENANT:
        raise HTTPException(status_code=429, detail="Too many AI requests are already in progress")

    if execution.kind == "widget_reply":
        conversation = await db.scalar(
            select(Conversation)
            .where(
                Conversation.organization_id == user.organization_id,
                Conversation.id == execution.conversation_id,
            )
            .with_for_update()
        )
        if (
            conversation is None
            or conversation.ai_mode != "ai"
            or conversation.ai_agent_id != execution.ai_agent_id
        ):
            raise HTTPException(
                status_code=409,
                detail="The conversation has been taken over or routed to another AI bot",
            )
        latest_message_id = await db.scalar(
            select(Message.id)
            .where(
                Message.organization_id == user.organization_id,
                Message.conversation_id == conversation.id,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        if latest_message_id != execution.source_message_id:
            raise HTTPException(
                status_code=409,
                detail="A newer conversation message exists; retry the latest customer message instead",
            )

    now = datetime.now(UTC)
    execution.status = "queued"
    execution.attempt_count = 0
    execution.manual_retry_count += 1
    execution.last_manual_retry_by_user_id = user.id
    execution.last_manual_retry_at = now
    execution.next_attempt_at = now
    execution.started_at = None
    execution.completed_at = None
    execution.error_code = None
    execution.safe_summary = None
    execution.draft = None
    execution.recommendation_result = None
    execution.citations = []
    execution.tool_outcomes = []
    execution.usage = {}
    execution.model_name = None
    if execution.kind == "widget_reply":
        execution.reply_status = "processing"
    await db.flush()
    logger.info(
        "ai_execution_manually_requeued",
        extra={
            "organization_id": str(user.organization_id),
            "execution_id": str(execution.id),
            "actor_user_id": str(user.id),
            "manual_retry_count": execution.manual_retry_count,
            "kind": execution.kind,
        },
    )
    return AIExecutionRetryOut(
        id=execution.id,
        status="queued",
        manual_retry_count=execution.manual_retry_count,
        message="The AI execution has been queued for another attempt.",
    )


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
    agent_name = await db.scalar(
        select(AIAgent.name).where(
            AIAgent.id == execution.ai_agent_id,
            AIAgent.organization_id == user.organization_id,
        )
    )
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
        ai_agent_name=agent_name or "Support assistant",
        correlation_id=execution.correlation_id,
        draft=execution.draft if execution.reply_status == "draft_ready" else None,
        safe_summary=execution.safe_summary,
        citations=execution.citations,
        updated_at=execution.updated_at,
    )
