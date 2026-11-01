"""Background execution and tenant-scoped retrieval for AI tasks."""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, literal_column, or_, select

from app.db.session import SessionLocal, set_tenant_context
from app.models import (
    AIExecution,
    Conversation,
    Customer,
    DocumentChunk,
    KnowledgeDocument,
    Message,
    SupportWidget,
    Ticket,
    WidgetOrderVerification,
)
from app.services.ai_execution import create_grounded_draft, is_provider_configured
from app.services.widget_ai import (
    AI_TEMPORARY_FAILURE_REPLY,
    VERIFIED_CANCELLATION_REPLY,
    format_verified_order_status,
    widget_clarification_reply,
    widget_greeting_reply,
    widget_is_cancellation_request,
    widget_missing_knowledge_reply,
    widget_request_needs_order_verification,
    widget_sensitive_reply,
)

logger = logging.getLogger(__name__)
LEASE_TIMEOUT = timedelta(minutes=3)
RETRIEVAL_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "can", "could", "do", "does",
        "for", "from", "have", "how", "i", "in", "is", "it", "me", "my", "of",
        "on", "or", "our", "please", "the", "this", "to", "we", "what", "when",
        "where", "which", "who", "why", "with", "would", "you", "your",
    }
)
NON_ORDER_NUMBER_WORDS = frozenset({"status", "update", "details", "detail", "tracking", "information", "number"})


def _safe_ai_failure_code(exc: Exception) -> str:
    """Classify known provider errors without recording response bodies or secrets."""
    safe_code = getattr(exc, "code", None)
    if isinstance(safe_code, str) and re.fullmatch(r"[a-z0-9_]{1,80}", safe_code):
        return safe_code
    message = str(exc)
    provider_status = re.fullmatch(r"AI provider returned HTTP (\d{3})", message)
    if provider_status:
        return f"provider_http_{provider_status.group(1)}"
    if message == "AI provider is not configured":
        return "provider_not_configured"
    if message == "AI provider URL must use HTTPS outside local development":
        return "provider_url_invalid"
    if message == "AI provider returned an empty draft":
        return "provider_empty_response"
    # Failures outside the provider call are commonly checkpoint/database or
    # graph execution errors. Keep the public code useful without exposing
    # exception text, SQL, prompt content, or credentials.
    return "ai_execution_failed"


def _question_order_number(question: str) -> str | None:
    match = re.search(r"#\s*([A-Za-z0-9][A-Za-z0-9-]{1,59})", question)
    if match is None:
        match = re.search(
            r"\border(?:\s+(?:number|no\.?))?\s+([A-Za-z0-9][A-Za-z0-9-]{2,59})\b",
            question,
            re.IGNORECASE,
        )
    if match is None:
        return None
    value = match.group(1).strip().lstrip("#")
    return None if value.casefold() in NON_ORDER_NUMBER_WORDS else value


async def verified_widget_order_reply(
    organization_id: UUID,
    conversation_id: UUID,
    question: str,
) -> tuple[bool, str | None]:
    """Reuse an unexpired OTP verification for the same conversation and order."""
    requested_number = _question_order_number(question)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        verification = await db.scalar(
            select(WidgetOrderVerification)
            .where(
                WidgetOrderVerification.organization_id == organization_id,
                WidgetOrderVerification.conversation_id == conversation_id,
                WidgetOrderVerification.status == "verified",
                WidgetOrderVerification.expires_at > datetime.now(UTC),
            )
            .order_by(WidgetOrderVerification.verified_at.desc())
            .limit(1)
        )
        if verification is None:
            return False, None
        if requested_number and requested_number.casefold() != verification.order_number.lstrip("#").casefold():
            return False, None
        email_encrypted = verification.customer_email_encrypted
        order_number = verification.order_number
        order_id = verification.shopify_order_id

    try:
        from app.api.routes.integrations import installation_for, map_order, valid_access_token
        from app.integrations.providers.shopify.orders import lookup_authorized_order
        from app.integrations.providers.shopify.security import decrypt_credential

        email = decrypt_credential(email_encrypted)
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            installation = await installation_for(db, organization_id)
            access_token = await valid_access_token(db, installation)
            shop_domain = installation.shop_domain
        order = await lookup_authorized_order(
            shop_domain=shop_domain,
            access_token=access_token,
            order_number=order_number,
            customer_email=email,
        )
        if order is None or order.get("id") != order_id:
            return False, None
        mapped = map_order(order)
        return True, format_verified_order_status(mapped, opening="I checked your verified order")
    except Exception as exc:  # noqa: BLE001 - fail closed while retaining the verified session.
        logger.warning(
            "Verified widget order lookup failed: organization_id=%s conversation_id=%s error_type=%s",
            organization_id,
            conversation_id,
            type(exc).__name__,
        )
        return True, "I’ve verified your order, but I’m having trouble checking its latest status right now. A support teammate can help."


async def claim_ai_execution(organization_id: UUID) -> UUID | None:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.organization_id == organization_id,
                AIExecution.attempt_count < AIExecution.max_attempts,
                or_(
                    and_(AIExecution.status == "queued", AIExecution.next_attempt_at <= now),
                    and_(AIExecution.status == "running", AIExecution.updated_at <= now - LEASE_TIMEOUT),
                ),
            )
            .order_by(AIExecution.created_at, AIExecution.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if execution is None:
            await db.rollback()
            return None
        execution.status = "running"
        execution.attempt_count += 1
        execution.started_at = now
        execution.error_code = None
        execution_id = execution.id
        await db.commit()
        return execution_id


async def fail_exhausted_ai_leases(organization_id: UUID) -> bool:
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.organization_id == organization_id,
                AIExecution.status == "running",
                AIExecution.attempt_count >= AIExecution.max_attempts,
                AIExecution.updated_at <= now - LEASE_TIMEOUT,
            )
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if execution is None:
            await db.rollback()
            return False
        execution.status = "failed"
        execution.integration_context_encrypted = None
        execution.error_code = "worker_lease_expired"
        if execution.kind == "widget_reply":
            execution.reply_status = "failed"
        execution.safe_summary = "The AI request could not be completed. You can create a new request."
        execution.completed_at = now
        await db.commit()
        return True


async def load_execution_context(organization_id: UUID, execution_id: UUID) -> tuple[
    AIExecution,
    str,
    list[dict[str, str]],
    list[dict[str, str | int]],
    list[dict[str, str | int]],
    list[dict[str, str | int]],
    dict[str, object],
] | None:
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AIExecution).where(
                AIExecution.id == execution_id,
                AIExecution.organization_id == organization_id,
                AIExecution.status == "running",
            )
        )
        if execution is None:
            return None

        question = execution.question
        integration_context: dict[str, object] = {}
        if execution.integration_context_encrypted:
            from app.integrations.providers.shopify.security import decrypt_credential

            decoded = json.loads(decrypt_credential(execution.integration_context_encrypted))
            if isinstance(decoded, dict):
                integration_context = decoded
        conversation_context: list[dict[str, str]] = []
        retrieval_text = question
        if execution.conversation_id:
            conversation = await db.scalar(
                select(Conversation).where(
                    Conversation.id == execution.conversation_id,
                    Conversation.organization_id == organization_id,
                )
            )
            if conversation is None:
                raise ValueError("Conversation unavailable")
            ticket = await db.scalar(
                select(Ticket).where(
                    Ticket.id == conversation.ticket_id,
                    Ticket.organization_id == organization_id,
                )
            )
            customer = await db.scalar(
                select(Customer).where(
                    Customer.id == ticket.customer_id,
                    Customer.organization_id == organization_id,
                )
            ) if ticket else None
            messages = list(await db.scalars(
                select(Message)
                .where(
                    Message.organization_id == organization_id,
                    Message.conversation_id == conversation.id,
                    Message.sender_type != "internal_note",
                )
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(12)
            ))
            messages.reverse()
            conversation_context = [
                {"sender": message.sender_type, "content": message.content[:2000]}
                for message in messages
            ]
            newest_customer_message = next(
                (message.content for message in reversed(messages) if message.sender_type == "customer"),
                "",
            )
            retrieval_text = f"{ticket.subject if ticket else ''} {newest_customer_message}"
            if execution.kind == "widget_reply":
                # The typed name/email collected by the widget is not identity proof,
                # so it is deliberately excluded from the prompt.
                question = f"Customer message: {execution.question[:2000]}"
                retrieval_text = execution.question
            else:
                question = (
                    f"Draft a reply to the latest customer message. Ticket: {ticket.subject if ticket else 'Support request'}. "
                    f"Customer: {customer.name if customer else 'Customer'}. Latest message: {newest_customer_message[:2000]}"
                )
        search_text = retrieval_text[:2000]
        terms = list(
            dict.fromkeys(
                term
                for term in re.findall(r"[a-z0-9]+", search_text.casefold())
                if len(term) > 2 and term not in RETRIEVAL_STOPWORDS
            )
        )[:32]
        if not terms:
            return execution, question, conversation_context, [], [], [], integration_context
        simple_config = literal_column("'simple'::regconfig")
        # Customer questions rarely repeat every word used in a policy. ORed,
        # sanitized terms keep retrieval tolerant while ranking still favors
        # documents that match several terms.
        ts_query = func.to_tsquery(simple_config, " | ".join(terms))
        rank = func.ts_rank(func.to_tsvector(simple_config, DocumentChunk.content), ts_query)
        rows = (await db.execute(
            select(DocumentChunk, KnowledgeDocument.name)
            .join(
                KnowledgeDocument,
                (KnowledgeDocument.organization_id == DocumentChunk.organization_id)
                & (KnowledgeDocument.id == DocumentChunk.document_id),
            )
            .where(
                DocumentChunk.organization_id == organization_id,
                KnowledgeDocument.status == "ready",
                KnowledgeDocument.deleted_at.is_(None),
                func.to_tsvector(simple_config, DocumentChunk.content).op("@@")(ts_query),
            )
            .order_by(rank.desc(), DocumentChunk.document_id, DocumentChunk.chunk_index)
            .limit(6)
        )).all()
        context = [
            {
                "document_id": str(chunk.document_id),
                "document_name": name,
                "chunk_index": chunk.chunk_index,
                "excerpt": " ".join(chunk.content.split())[:800],
            }
            for chunk, name in rows
        ]
        citations = [
            {
                "document_id": str(chunk.document_id),
                "document_name": name,
                "chunk_index": chunk.chunk_index,
                "excerpt": " ".join(chunk.content.split())[:320],
            }
            for chunk, name in rows
        ]
        outcomes: list[dict[str, str | int]] = [
            {"tool": "tenant_knowledge_search", "status": "completed", "result_count": len(rows)}
        ]
        if integration_context:
            outcomes.append(
                {"tool": "shopify_verified_order_lookup", "status": "completed", "result_count": 1}
            )
        return execution, question, conversation_context, context, citations, outcomes, integration_context


async def process_ai_execution(organization_id: UUID, execution_id: UUID) -> None:
    now = datetime.now(UTC)
    try:
        loaded = await load_execution_context(organization_id, execution_id)
        if loaded is None:
            return
        execution, question, transcript, context, citations, outcomes, integration_context = loaded
        if execution.kind == "widget_reply":
            if await widget_reply_is_stale(organization_id, execution_id):
                return
            delivery_status = "draft_ready" if execution.delivery_mode == "draft_only" else "sent"
            sensitive_reply = widget_sensitive_reply(execution.question)
            if sensitive_reply is not None:
                draft, safe_summary = sensitive_reply
                reply_status = "escalated"
                if widget_is_cancellation_request(execution.question):
                    order_verified, _order_reply = await verified_widget_order_reply(
                        organization_id, execution.conversation_id, execution.question
                    )
                    if order_verified:
                        draft = VERIFIED_CANCELLATION_REPLY
                        safe_summary = "A previously verified order cancellation still requires human approval."
                elif widget_request_needs_order_verification(execution.question):
                    order_verified, order_reply = await verified_widget_order_reply(
                        organization_id, execution.conversation_id, execution.question
                    )
                    if order_verified:
                        draft = order_reply or AI_TEMPORARY_FAILURE_REPLY
                        reply_status = (
                            "escalated"
                            if draft == AI_TEMPORARY_FAILURE_REPLY
                            else delivery_status
                        )
                        safe_summary = "A current Shopify order lookup used the shopper’s active email verification."
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=draft,
                    reply_status=reply_status,
                    safe_summary=safe_summary,
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
            greeting = widget_greeting_reply(execution.question)
            if greeting is not None:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=greeting,
                    reply_status=delivery_status,
                    safe_summary="A conversational reply was prepared without using private customer or order data.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
            clarification = widget_clarification_reply(execution.question, transcript)
            if clarification is not None:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=clarification,
                    reply_status=delivery_status,
                    safe_summary="A deterministic clarification explained the active support workflow without a model call.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
            if not context:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=widget_missing_knowledge_reply(execution.question),
                    reply_status="escalated",
                    safe_summary="No matching tenant knowledge was found. The shopper received a clear next step without unsupported claims.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
            if not is_provider_configured():
                logger.warning("Widget AI provider is not configured: execution_id=%s", execution_id)
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=AI_TEMPORARY_FAILURE_REPLY,
                    reply_status="escalated",
                    safe_summary="The AI provider is unavailable. A safe handoff reply was prepared.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
                return
        result = await create_grounded_draft(
            organization_id=organization_id,
            execution_id=execution_id,
            question=question,
            instructions=execution.instructions,
            conversation_context=transcript,
            knowledge_context=context,
            integration_context=integration_context,
            auto_reply=(execution.kind == "widget_reply" and execution.delivery_mode == "auto_reply"),
        )
        if execution.kind == "widget_reply":
            await finish_widget_reply(
                organization_id,
                execution_id,
                draft=str(result.get("draft", ""))[:12000],
                reply_status="draft_ready" if execution.delivery_mode == "draft_only" else "sent",
                safe_summary=f"Reply grounded in {len(citations)} tenant knowledge source(s).",
                citations=citations,
                outcomes=outcomes,
                usage=result.get("usage", {}) if isinstance(result.get("usage"), dict) else {},
                model_name=str(result.get("model_name", ""))[:120] or None,
            )
            return
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            row = await db.scalar(
                select(AIExecution).where(
                    AIExecution.id == execution_id,
                    AIExecution.organization_id == organization_id,
                    AIExecution.status == "running",
                )
            )
            if row is None:
                await db.rollback()
                return
            row.status = "succeeded"
            row.integration_context_encrypted = None
            row.draft = str(result.get("draft", ""))[:12000]
            output_label = "Reply draft" if row.kind == "reply_draft" else "Playground answer"
            row.safe_summary = f"{output_label} generated using {len(citations)} knowledge source(s)."
            row.citations = citations
            row.tool_outcomes = outcomes
            raw_usage = result.get("usage", {})
            row.usage = raw_usage if isinstance(raw_usage, dict) else {}
            row.model_name = str(result.get("model_name", ""))[:120] or None
            row.error_code = None
            row.completed_at = now
            await db.commit()
    except Exception as exc:  # noqa: BLE001 - record failures safely and keep the worker alive
        failure_code = _safe_ai_failure_code(exc)
        logger.warning(
            "AI execution failed: execution_id=%s error_type=%s failure_code=%s",
            execution_id,
            type(exc).__name__,
            failure_code,
        )
        widget_fallback_mode: str | None = None
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            row = await db.scalar(
                select(AIExecution)
                .where(
                    AIExecution.id == execution_id,
                    AIExecution.organization_id == organization_id,
                    AIExecution.status == "running",
                )
                .with_for_update()
            )
            if row is None:
                await db.rollback()
                return
            exhausted = row.attempt_count >= row.max_attempts
            if exhausted and row.kind == "widget_reply":
                widget_fallback_mode = row.delivery_mode
                await db.rollback()
            else:
                row.status = "failed" if exhausted else "queued"
                if row.kind == "widget_reply":
                    row.reply_status = "failed" if exhausted else "processing"
                if exhausted:
                    row.integration_context_encrypted = None
                row.error_code = failure_code
                row.safe_summary = (
                    "The AI request could not be completed. You can create a new request."
                    if exhausted
                    else None
                )
                row.next_attempt_at = now + timedelta(seconds=min(5 * (2 ** (row.attempt_count - 1)), 60))
                row.completed_at = now if exhausted else None
                await db.commit()
        if widget_fallback_mode is not None:
            try:
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=AI_TEMPORARY_FAILURE_REPLY,
                    reply_status="escalated",
                    safe_summary="AI generation failed after its retry limit. A safe handoff reply was prepared.",
                    citations=[],
                    outcomes=[],
                    usage={},
                    model_name=None,
                )
            except Exception as fallback_exc:  # noqa: BLE001 - keep the worker alive if persistence is unavailable.
                logger.error(
                    "AI widget fallback persistence failed: execution_id=%s error_type=%s",
                    execution_id,
                    type(fallback_exc).__name__,
                )


async def widget_reply_is_stale(organization_id: UUID, execution_id: UUID) -> bool:
    """Skip work when an agent took over or a newer visitor message superseded it."""
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        execution = await db.scalar(
            select(AIExecution).where(
                AIExecution.id == execution_id,
                AIExecution.organization_id == organization_id,
                AIExecution.kind == "widget_reply",
                AIExecution.status == "running",
            )
        )
        if execution is None or execution.source_message_id is None:
            return True
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == execution.conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        if conversation is None or conversation.ai_mode != "ai":
            execution.status = "succeeded"
            execution.reply_status = "escalated"
            execution.safe_summary = "A teammate switched this conversation to Human mode. No AI reply was sent."
            execution.draft = None
            execution.completed_at = datetime.now(UTC)
            await db.commit()
            return True
        source = await db.scalar(
            select(Message).where(
                Message.id == execution.source_message_id,
                Message.organization_id == organization_id,
                Message.conversation_id == execution.conversation_id,
            )
        )
        if source is None:
            return True
        newer_customer = await db.scalar(
            select(Message.id)
            .where(
                Message.organization_id == organization_id,
                Message.conversation_id == execution.conversation_id,
                Message.sender_type == "customer",
                (Message.created_at > source.created_at)
                | ((Message.created_at == source.created_at) & (Message.id > source.id)),
            )
            .limit(1)
        )
        agent_took_over = await db.scalar(
            select(Message.id)
            .where(
                Message.organization_id == organization_id,
                Message.conversation_id == execution.conversation_id,
                Message.sender_type.in_(("agent", "internal_note")),
                Message.created_at >= source.created_at,
            )
            .limit(1)
        )
        if newer_customer or agent_took_over:
            execution.status = "succeeded"
            execution.reply_status = "escalated"
            execution.safe_summary = (
                "A newer message or teammate response took priority. No AI reply was sent."
            )
            execution.draft = None
            execution.completed_at = datetime.now(UTC)
            await db.commit()
            return True
        return False


async def finish_widget_reply(
    organization_id: UUID,
    execution_id: UUID,
    *,
    draft: str,
    reply_status: str,
    safe_summary: str,
    citations: list[dict[str, str | int]],
    outcomes: list[dict[str, str | int]],
    usage: dict[str, int],
    model_name: str | None,
) -> None:
    """Persist a draft or send only while holding the conversation row lock."""
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        row = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.id == execution_id,
                AIExecution.organization_id == organization_id,
                AIExecution.kind == "widget_reply",
                AIExecution.status == "running",
            )
            .with_for_update()
        )
        if row is None or row.conversation_id is None or row.source_message_id is None:
            await db.rollback()
            return
        conversation = await db.scalar(
            select(Conversation)
            .where(
                Conversation.id == row.conversation_id,
                Conversation.organization_id == organization_id,
            )
            .with_for_update()
        )
        source = await db.scalar(
            select(Message).where(
                Message.id == row.source_message_id,
                Message.organization_id == organization_id,
                Message.conversation_id == row.conversation_id,
            )
        )
        if conversation is None or source is None:
            await db.rollback()
            return
        if conversation.ai_mode != "ai":
            row.status = "succeeded"
            row.reply_status = "escalated"
            row.safe_summary = "A teammate switched this conversation to Human mode. No AI reply was sent."
            row.draft = None
            row.completed_at = now
            await db.commit()
            return
        widget = await db.scalar(
            select(SupportWidget)
            .where(SupportWidget.organization_id == organization_id)
            .with_for_update()
        )
        latest = await db.scalar(
            select(Message)
            .where(
                Message.organization_id == organization_id,
                Message.conversation_id == row.conversation_id,
                Message.sender_type != "internal_note",
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
        agent_after = await db.scalar(
            select(Message.id)
            .where(
                Message.organization_id == organization_id,
                Message.conversation_id == row.conversation_id,
                Message.sender_type.in_(("agent", "internal_note")),
                Message.created_at >= source.created_at,
            )
            .limit(1)
        )
        if latest is None or latest.id != source.id or agent_after:
            row.status = "succeeded"
            row.reply_status = "escalated"
            row.safe_summary = "A newer message or teammate response took priority. No AI reply was sent."
            row.draft = None
            row.completed_at = now
            await db.commit()
            return
        if widget is None or not widget.enabled or not widget.ai_enabled:
            reply_status = "escalated"
            safe_summary = "AI replies were disabled before this response could be delivered."
        elif row.delivery_mode == "auto_reply" and widget.ai_reply_mode != "auto_reply":
            reply_status = "draft_ready"
            safe_summary = "The workspace changed to draft-only mode before delivery. Review this response before sending."
        row.status = "succeeded"
        row.reply_status = reply_status
        row.draft = draft
        row.safe_summary = safe_summary
        row.citations = citations
        row.tool_outcomes = outcomes
        row.usage = usage
        row.model_name = model_name
        row.error_code = None
        row.completed_at = now
        if reply_status == "sent" or (reply_status == "escalated" and row.delivery_mode == "auto_reply" and widget is not None and widget.ai_enabled and widget.enabled):
            db.add(
                Message(
                    organization_id=organization_id,
                    conversation_id=conversation.id,
                    sender_type="assistant",
                    sender_user_id=None,
                    content=draft,
                    content_type="text",
                )
            )
            conversation.updated_at = now
            ticket = await db.scalar(
                select(Ticket).where(
                    Ticket.id == conversation.ticket_id,
                    Ticket.organization_id == organization_id,
                )
            )
            if ticket is not None:
                ticket.updated_at = now
        await db.commit()
