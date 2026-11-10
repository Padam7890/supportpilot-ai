"""Tenant-scoped conversation and knowledge context assembly for AI runs."""

import json
from uuid import UUID

from sqlalchemy import select, tuple_

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.conversation_understanding import understand_conversation_turn
from app.features.ai.application.topic_state_runtime import resolve_and_record_topic
from app.features.ai.application.evidence_assessment import assess_knowledge_evidence
from app.features.ai.application.conversational_intents import (
    should_skip_knowledge_retrieval,
)
from app.features.ai.application.follow_up import PENDING_KEY
from app.features.ai.application.retrieval_search import search_agent_knowledge
from app.features.ai.application.widget_stream_context import STREAM_SOURCE_IDS_KEY
from app.models import (
    AIAgent,
    AIExecution,
    Conversation,
    Message,
    Ticket,
)


async def load_execution_context(
    organization_id: UUID, execution_id: UUID, *, include_knowledge: bool | None = None,
    follow_up_query: str | None = None
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
            message_query = select(Message).where(
                Message.organization_id == organization_id,
                Message.conversation_id == conversation.id,
                Message.sender_type != "internal_note",
            )
            if execution.kind == "widget_reply" and execution.source_message_id:
                source = select(Message.created_at, Message.id).where(
                    Message.organization_id == organization_id,
                    Message.conversation_id == conversation.id,
                    Message.id == execution.source_message_id,
                )
                message_query = message_query.where(
                    tuple_(Message.created_at, Message.id) <= source.scalar_subquery()
                )
            messages = list(await db.scalars(
                message_query.order_by(Message.created_at.desc(), Message.id.desc()).limit(12)
            ))
            messages.reverse()
            conversation_context = [
                {
                    "sender": message.sender_type, "content": message.content[:2000],
                    "created_at": message.created_at.isoformat(),
                    **(
                        {PENDING_KEY: json.dumps(message.provider_metadata[PENDING_KEY])}
                        if message.sender_type == "assistant"
                        and PENDING_KEY in (message.provider_metadata or {}) else {}
                    ),
                    **(
                        {STREAM_SOURCE_IDS_KEY: json.dumps(message.provider_metadata[STREAM_SOURCE_IDS_KEY])}
                        if message.sender_type == "assistant"
                        and STREAM_SOURCE_IDS_KEY in (message.provider_metadata or {}) else {}
                    ),
                }
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
                question = execution.question[:2000]
                # Resolve underspecified follow-ups against one preceding customer
                # turn only; previous assistant text is never retrieval evidence.
                understanding = understand_conversation_turn(
                    execution.question,
                    conversation_context,
                    agent_id=execution.ai_agent_id,
                )
                # A delayed/retried execution must not overwrite a newer topic.
                latest_customer_id = await db.scalar(
                    select(Message.id).where(
                        Message.organization_id == organization_id,
                        Message.conversation_id == conversation.id,
                        Message.sender_type == "customer",
                    ).order_by(Message.created_at.desc(), Message.id.desc()).limit(1)
                )
                if execution.source_message_id == latest_customer_id:
                    retrieval_text = await resolve_and_record_topic(
                        db,
                        organization_id=organization_id,
                        conversation_id=conversation.id,
                        agent_id=execution.ai_agent_id,
                        message=execution.question,
                        prior_transcript=conversation_context[:-1] if conversation_context
                        and conversation_context[-1].get("sender") == "customer"
                        and conversation_context[-1].get("content", "").strip() == execution.question.strip()
                        else conversation_context,
                        retrieval_query=understanding.retrieval_query,
                        explicit_topic=understanding.topic_switch,
                    )
                    await db.commit()
                    await set_tenant_context(db, organization_id)
            else:
                question = newest_customer_message[:2000] or question
        if execution.kind == "playground" and execution.playground_history:
            understanding = understand_conversation_turn(
                question,
                conversation_context,
                agent_id=execution.ai_agent_id,
            )
            retrieval_text = understanding.retrieval_query
        search_text = (follow_up_query or retrieval_text)[:2000]
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
        if execution.kind == "playground":
            from app.features.ai.application.conversation_orchestration import plan_playground_turn

            if plan_playground_turn(question, conversation_context) is not None:
                return execution, question, conversation_context, [], [], [], integration_context
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
        # Diagnostic only: lexical overlap does not establish factual entailment.
        evidence = assess_knowledge_evidence(
            search_text, [match.excerpt[:800] for match in search_result.matches]
        )
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
                "evidence_signal": evidence.reason,
                "evidence_overlap_terms": len(evidence.matched_terms),
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
