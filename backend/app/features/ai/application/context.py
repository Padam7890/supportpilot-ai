"""Tenant-scoped conversation and knowledge context assembly for AI runs."""

import json
import re
from uuid import UUID

from sqlalchemy import func, literal_column, select

from app.db.session import SessionLocal, set_tenant_context
from app.models import (
    AIExecution,
    Conversation,
    Customer,
    DocumentChunk,
    KnowledgeDocument,
    Message,
    Ticket,
)

RETRIEVAL_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "can",
        "could",
        "do",
        "does",
        "for",
        "from",
        "have",
        "how",
        "i",
        "in",
        "is",
        "it",
        "me",
        "my",
        "of",
        "on",
        "or",
        "our",
        "please",
        "the",
        "this",
        "to",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "with",
        "would",
        "you",
        "your",
    }
)


async def load_execution_context(
    organization_id: UUID, execution_id: UUID
) -> (
    tuple[
        AIExecution,
        str,
        list[dict[str, str]],
        list[dict[str, str | int]],
        list[dict[str, str | int]],
        list[dict[str, str | int]],
        dict[str, object],
    ]
    | None
):
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
            customer = (
                await db.scalar(
                    select(Customer).where(
                        Customer.id == ticket.customer_id,
                        Customer.organization_id == organization_id,
                    )
                )
                if ticket
                else None
            )
            messages = list(
                await db.scalars(
                    select(Message)
                    .where(
                        Message.organization_id == organization_id,
                        Message.conversation_id == conversation.id,
                        Message.sender_type != "internal_note",
                    )
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(12)
                )
            )
            messages.reverse()
            conversation_context = [
                {"sender": message.sender_type, "content": message.content[:2000]}
                for message in messages
            ]
            newest_customer_message = next(
                (
                    message.content
                    for message in reversed(messages)
                    if message.sender_type == "customer"
                ),
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
        rows = (
            await db.execute(
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
            )
        ).all()
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
        return (
            execution,
            question,
            conversation_context,
            context,
            citations,
            outcomes,
            integration_context,
        )
