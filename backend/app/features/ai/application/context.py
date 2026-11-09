"""Tenant-scoped conversation and knowledge context assembly for AI runs."""

import json
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.conversational_intents import (
    classify_conversational_intent,
    should_skip_knowledge_retrieval,
)
from app.features.ai.application.retrieval import is_contextual_follow_up
from app.features.ai.application.retrieval_search import search_agent_knowledge
from app.models import (
    AIAgent,
    AIExecution,
    Conversation,
    Customer,
    Message,
    Ticket,
)


async def load_execution_context(
    organization_id: UUID, execution_id: UUID, *, include_knowledge: bool | None = None
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
        if execution.kind == "playground" and execution.playground_history:
            conversation_context = [
                {"sender": turn["role"], "content": turn["content"][:600]}
                for turn in execution.playground_history[-6:]
                if turn.get("role") in {"user", "assistant"}
                and isinstance(turn.get("content"), str)
            ]
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
                # Short follow-ups often omit the topic (for example, "how long
                # does it take?"). Carry only a few earlier customer turns into
                # retrieval so the search remains bounded and never treats an AI
                # answer as evidence about what the shopper asked.
                prior_customer_questions = (
                    [
                        message.content[:240]
                        for message in messages
                        if message.sender_type == "customer"
                        and message.id != execution.source_message_id
                    ][-2:]
                    if is_contextual_follow_up(execution.question)
                    else []
                )
                retrieval_text = " ".join([*prior_customer_questions, execution.question[:1200]])
            else:
                question = (
                    f"Draft a reply to the latest customer message. Ticket: {ticket.subject if ticket else 'Support request'}. "
                    f"Customer: {customer.name if customer else 'Customer'}. Latest message: {newest_customer_message[:2000]}"
                )
        if execution.kind == "playground" and execution.playground_history:
            previous_questions = (
                [
                    turn.get("content", "")[:240]
                    for turn in execution.playground_history[-6:]
                    if turn.get("role") == "user" and isinstance(turn.get("content"), str)
                ][-2:]
                if is_contextual_follow_up(question)
                else []
            )
            retrieval_text = " ".join([*previous_questions, question])
        search_text = retrieval_text[:2000]
        agent = await db.scalar(
            select(AIAgent).where(
                AIAgent.organization_id == organization_id,
                AIAgent.id == execution.ai_agent_id,
                AIAgent.status == "active",
            )
        )
        if agent is None:
            execution.instructions = None
        else:
            # New jobs use the configuration captured alongside their version.
            # Legacy queued jobs have no snapshot and retain the prior behavior.
            agent_instructions = (
                execution.ai_agent_instructions_snapshot
                if execution.ai_agent_instructions_snapshot is not None
                else agent.system_instructions
            ).strip()[:8000]
            request_instructions = (execution.instructions or "").strip()[:1000]
            execution.instructions = "\n\n".join(
                item for item in (agent_instructions, request_instructions) if item
            )[:9000]
        channel = "playground" if execution.kind == "playground" else "widget"
        if include_knowledge is False or (
            include_knowledge is None and execution.kind == "widget_reply"
        ) or should_skip_knowledge_retrieval(execution.question, channel=channel):
            return execution, question, conversation_context, [], [], [], integration_context
        search_result = (
            await search_agent_knowledge(
                db,
                organization_id=organization_id,
                ai_agent_id=agent.id,
                search_text=search_text,
            )
            if agent is not None
            else None
        )
        if search_result is None:
            return execution, question, conversation_context, [], [], [], integration_context
        context = [
            {
                "document_id": str(match.document_id),
                "document_name": match.document_name,
                "knowledge_base_name": match.knowledge_base_name,
                "chunk_index": match.chunk_index,
                "excerpt": match.excerpt[:800],
            }
            for match in search_result.matches
        ]
        citations = [
            {
                "document_id": str(match.document_id),
                "document_name": match.document_name,
                "knowledge_base_name": match.knowledge_base_name,
                "chunk_index": match.chunk_index,
                "excerpt": match.excerpt[:320],
                "match_basis": match.match_basis,
                "rrf_score": match.rrf_score,
                "semantic_similarity": match.semantic_similarity,
                "keyword_rank": match.keyword_rank,
                "semantic_rank": match.semantic_rank,
            }
            for match in search_result.matches
        ]
        outcomes: list[dict[str, str | int]] = [
            {
                "tool": "tenant_knowledge_search",
                "status": "completed",
                "result_count": len(search_result.matches),
                "retrieval_method": search_result.retrieval_method,
                "latency_ms": search_result.retrieval_latency_ms,
                "keyword_candidates": search_result.keyword_candidate_count,
                "semantic_candidates": search_result.semantic_candidate_count,
                "embedding_status": search_result.embedding_status,
                "embedding_coverage": search_result.embedding_coverage,
                "retrieval_outcome": search_result.retrieval_outcome,
            }
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
