"""Tenant-safe widget reply gating, recommendation routing, and persistence."""

import logging
import re
from datetime import UTC, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.domain.policies import widget_reply_is_superseded
from app.features.ai.application.retrieval_search import citations_remain_authorized
from app.features.ai.tools.recommendations import ToolReference
from app.features.notifications.application.events import TicketNotificationPayload, enqueue_notification_event
from app.models import (
    AIExecution,
    AIAgent,
    Conversation,
    Message,
    RecommendationEvent,
    SupportWidget,
    Ticket,
)
from app.services.recommendation_conversation import process_widget_shopping_turn

logger = logging.getLogger(__name__)


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
        active_agent = await db.scalar(
            select(AIAgent.id).where(
                AIAgent.id == execution.ai_agent_id,
                AIAgent.organization_id == organization_id,
                AIAgent.status == "active",
            )
        )
        if active_agent is None:
            execution.status = "succeeded"
            execution.reply_status = "escalated"
            execution.safe_summary = "The selected AI bot is inactive. No automated response was generated."
            execution.draft = None
            execution.completed_at = datetime.now(UTC)
            await db.commit()
            return True
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == execution.conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        if conversation is None:
            return True
        if conversation.ai_agent_id != execution.ai_agent_id:
            execution.status = "succeeded"
            execution.reply_status = "escalated"
            execution.safe_summary = (
                "A teammate changed the bot for this conversation. The older bot reply was suppressed."
            )
            execution.draft = None
            execution.completed_at = datetime.now(UTC)
            await db.commit()
            return True
        suppression = widget_reply_is_superseded(
            ai_mode=conversation.ai_mode,
            source_is_latest=True,
            teammate_replied=False,
        )
        if suppression == "human_takeover":
            execution.status = "succeeded"
            execution.reply_status = "escalated"
            execution.safe_summary = (
                "A teammate switched this conversation to Human mode. No AI reply was sent."
            )
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
        suppression = widget_reply_is_superseded(
            ai_mode=conversation.ai_mode,
            source_is_latest=newer_customer is None,
            teammate_replied=agent_took_over is not None,
        )
        if suppression:
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


async def process_widget_shopping_execution(
    organization_id: UUID,
    execution_id: UUID,
    *,
    question: str,
) -> bool:
    """Run the closed recommendation tools against compact conversation state.

    A transaction-scoped advisory lock serializes recommendation turns for one
    conversation across worker processes. The response writer separately locks
    the conversation and checks that the source message is still current.
    """
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
        if execution is None or execution.conversation_id is None:
            await db.rollback()
            return True
        conversation_id = execution.conversation_id
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            lock_key = int.from_bytes(conversation_id.bytes[:8], "big", signed=True)
            await db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key}
            )
        conversation = await db.scalar(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.organization_id == organization_id,
            )
        )
        if conversation is None:
            await db.rollback()
            return True
        agent = await db.scalar(
            select(AIAgent).where(
                AIAgent.id == execution.ai_agent_id,
                AIAgent.organization_id == organization_id,
                AIAgent.status == "active",
            )
        )
        if agent is None:
            execution.status = "succeeded"
            execution.reply_status = "escalated"
            execution.safe_summary = "The selected AI bot is inactive. No automated response was generated."
            execution.draft = None
            execution.completed_at = datetime.now(UTC)
            await db.commit()
            return True
        if execution.ai_agent_tools_snapshot is None:
            # Older queued executions predate tool snapshots. Use the tenant's
            # currently configured bot allowlist, and fail closed if unavailable.
            allowed_tools = list(agent.allowed_tools or [])
        else:
            allowed_tools = list(execution.ai_agent_tools_snapshot)
        source_message = await db.scalar(
            select(Message).where(
                Message.organization_id == organization_id,
                Message.conversation_id == conversation_id,
                Message.id == execution.source_message_id,
            )
        )
        selected_references: list[ToolReference] | None = None
        if source_message is not None:
            raw_selections = source_message.provider_metadata.get("recommendation_selections")
            if isinstance(raw_selections, list):
                selected_references = [
                    ToolReference.model_validate(item) for item in raw_selections
                ]
        outcome = await process_widget_shopping_turn(
            db,
            organization_id,
            conversation_id,
            question,
            conversation.shopping_state,
            conversation.shopping_state_expires_at,
            selected_references=selected_references,
            allowed_tools=allowed_tools,
        )
        if not outcome.handled:
            await db.rollback()
            return False
        await finish_widget_reply(
            organization_id,
            execution_id,
            draft=outcome.draft or "Could you clarify what product you are looking for?",
            reply_status="draft_ready" if execution.delivery_mode == "draft_only" else "sent",
            safe_summary="A shopping response was grounded in this tenant’s catalog and conversation preferences.",
            citations=[],
            outcomes=outcome.tool_outcomes or [],
            usage=outcome.usage or {},
            model_name=outcome.model_name,
            shopping_state=outcome.state,
            persist_shopping_state=True,
            displayed_recommendations=outcome.displayed_recommendations,
            recommendation_payload=outcome.recommendation_payload,
            switch_to_human=outcome.switch_to_human,
        )
        await db.commit()
        return True


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
    shopping_state: dict | None = None,
    persist_shopping_state: bool = False,
    displayed_recommendations: list[dict[str, object]] | None = None,
    recommendation_payload: dict[str, object] | None = None,
    switch_to_human: bool = False,
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
        active_agent = await db.scalar(
            select(AIAgent)
            .where(
                AIAgent.id == row.ai_agent_id,
                AIAgent.organization_id == organization_id,
                AIAgent.status == "active",
            )
            .with_for_update()
        )
        if active_agent is None:
            row.status = "succeeded"
            row.reply_status = "escalated"
            row.safe_summary = "The selected AI bot was deactivated before reply delivery. No automated response was generated."
            row.draft = None
            row.completed_at = now
            await db.commit()
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
        if conversation.ai_agent_id != row.ai_agent_id:
            row.status = "succeeded"
            row.reply_status = "escalated"
            row.safe_summary = (
                "A teammate changed the bot for this conversation. The older bot reply was suppressed."
            )
            row.draft = None
            row.completed_at = now
            await db.commit()
            return
        if not await citations_remain_authorized(
            db,
            organization_id=organization_id,
            ai_agent_id=row.ai_agent_id,
            citations=citations,
        ):
            row.status = "succeeded"
            row.reply_status = "escalated"
            row.safe_summary = (
                "A cited knowledge source was removed or changed before this reply completed. "
                "The response was suppressed for review."
            )
            row.draft = None
            row.citations = []
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
        suppression = widget_reply_is_superseded(
            ai_mode=conversation.ai_mode,
            source_is_latest=latest is not None and latest.id == source.id,
            teammate_replied=agent_after is not None,
        )
        if suppression == "human_takeover":
            row.status = "succeeded"
            row.reply_status = "escalated"
            row.safe_summary = (
                "A teammate switched this conversation to Human mode. No AI reply was sent."
            )
            row.draft = None
            row.completed_at = now
            await db.commit()
            return
        if suppression:
            row.status = "succeeded"
            row.reply_status = "escalated"
            row.safe_summary = (
                "A newer message or teammate response took priority. No AI reply was sent."
            )
            row.draft = None
            row.completed_at = now
            await db.commit()
            return
        if persist_shopping_state:
            if shopping_state is None:
                conversation.shopping_state = None
                conversation.shopping_state_updated_at = None
                conversation.shopping_state_expires_at = None
            else:
                conversation.shopping_state = shopping_state
                conversation.shopping_state_updated_at = now
                conversation.shopping_state_expires_at = now + timedelta(days=30)
                if displayed_recommendations is not None:
                    conversation.shopping_state = {
                        **shopping_state,
                        "last_displayed_recommendations": displayed_recommendations[:5],
                    }
            if switch_to_human:
                conversation.ai_mode = "human"
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
        if reply_status == "escalated":
            await enqueue_notification_event(
                db,
                organization_id=organization_id,
                event_type="ai.escalation_required",
                aggregate_type="ticket",
                aggregate_id=conversation.ticket_id,
                event_id=uuid5(NAMESPACE_URL, f"ai-escalation:{row.id}"),
                payload=TicketNotificationPayload(
                    ticket_id=conversation.ticket_id,
                    conversation_id=conversation.id,
                ),
            )
        if reply_status == "sent" or (
            reply_status == "escalated"
            and row.delivery_mode == "auto_reply"
            and widget is not None
            and widget.ai_enabled
            and widget.enabled
        ):
            inserted_assistant_id = await db.scalar(
                pg_insert(Message)
                .values(
                    organization_id=organization_id,
                    conversation_id=conversation.id,
                    sender_type="assistant",
                    sender_user_id=None,
                    content=draft,
                    content_type="text",
                    source_ai_execution_id=row.id,
                    provider_metadata=(
                        {"recommendation": recommendation_payload}
                        if recommendation_payload is not None
                        else {}
                    ),
                )
                .on_conflict_do_nothing(constraint="uq_messages_org_ai_execution")
                .returning(Message.id)
            )
            if inserted_assistant_id is not None:
                conversation.updated_at = now
                ticket = await db.scalar(
                    select(Ticket).where(
                        Ticket.id == conversation.ticket_id,
                        Ticket.organization_id == organization_id,
                    )
                )
                if ticket is not None:
                    ticket.updated_at = now
        if recommendation_payload is not None:
            response_type = recommendation_payload.get("response_type")
            event_type = (
                "no_result"
                if response_type == "no_match"
                else "comparison"
                if response_type == "comparison"
                else None
            )
            if event_type:
                criteria = recommendation_payload.get("applied_criteria")
                category = criteria.get("category") if isinstance(criteria, dict) else None
                category_text = str(category).strip() if category is not None else ""
                safe_category = (
                    category_text[:120]
                    if re.fullmatch(r"[\wÀ-ÿ -]{1,80}", category_text)
                    and not re.search(r"\d{4,}", category_text)
                    else None
                )
                event_name = f"{event_type}:{row.source_message_id}"
                await db.execute(
                    pg_insert(RecommendationEvent)
                    .values(
                        organization_id=organization_id,
                        event_id=uuid5(NAMESPACE_URL, event_name),
                        conversation_id=conversation.id,
                        message_id=row.source_message_id,
                        event_type=event_type,
                        query_category=safe_category,
                    )
                    .on_conflict_do_nothing(constraint="uq_recommendation_events_org_event")
                )
        shopping_handoff = any(
            isinstance(item, dict)
            and item.get("tool") == "shopping_state"
            and item.get("status") in {"handoff", "handoff_offer", "unsupported"}
            for item in outcomes
        )
        if shopping_handoff and row.source_message_id is not None:
            await db.execute(
                pg_insert(RecommendationEvent)
                .values(
                    organization_id=organization_id,
                    event_id=uuid5(NAMESPACE_URL, f"human_handoff:{row.source_message_id}"),
                    conversation_id=conversation.id,
                    message_id=row.source_message_id,
                    event_type="human_handoff",
                )
                .on_conflict_do_nothing(constraint="uq_recommendation_events_org_event")
            )
        await db.commit()
