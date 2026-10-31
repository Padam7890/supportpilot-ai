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
)
from app.services.ai_execution import create_grounded_draft
from app.services.widget_ai import (
    HANDOFF_MESSAGE,
    widget_greeting_reply,
    widget_request_needs_human,
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
            from app.services.shopify_security import decrypt_credential

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
            if widget_request_needs_human(execution.question):
                await finish_widget_reply(
                    organization_id,
                    execution_id,
                    draft=HANDOFF_MESSAGE,
                    reply_status="escalated",
                    safe_summary="This request needs a support teammate. No private order or account data was disclosed.",
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
                    reply_status="draft_ready" if execution.delivery_mode == "draft_only" else "sent",
                    safe_summary="A short greeting reply was prepared without using private customer or order data.",
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
                    draft=HANDOFF_MESSAGE,
                    reply_status="escalated",
                    safe_summary="No matching tenant knowledge was found. A support teammate needs to answer.",
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
        logger.warning(
            "AI execution failed (%s)",
            type(exc).__name__,
            extra={"execution_id": str(execution_id), "error_type": type(exc).__name__},
        )
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
            row.status = "failed" if exhausted else "queued"
            if row.kind == "widget_reply":
                row.reply_status = "failed" if exhausted else "processing"
            if exhausted:
                row.integration_context_encrypted = None
            row.error_code = "generation_failed"
            row.safe_summary = (
                "The AI request could not be completed. You can create a new request."
                if exhausted
                else None
            )
            row.next_attempt_at = now + timedelta(seconds=min(5 * (2 ** (row.attempt_count - 1)), 60))
            row.completed_at = now if exhausted else None
            await db.commit()


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
