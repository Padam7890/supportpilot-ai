"""Persist generated non-widget replies after tenant and source revalidation."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.guarded_generation import GuardedDraft
from app.features.ai.application.retrieval_search import citations_remain_authorized
from app.models import AIAgent, AIExecution


async def complete_non_widget_generated_reply(
    organization_id: UUID,
    execution_id: UUID,
    *,
    guarded: GuardedDraft,
    completed_at: datetime,
) -> None:
    """Lock execution, recheck agent and citations, then persist a safe answer."""
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
            draft = "This AI bot is inactive. Activate it and run the request again."
            summary = "The selected AI bot was deactivated before the answer completed."
            citations = []
            outcomes = None
            usage = None
            model_name = None
        elif not await citations_remain_authorized(
            db,
            organization_id=organization_id,
            ai_agent_id=row.ai_agent_id,
            citations=guarded.citations,
        ):
            draft = (
                "A knowledge source used for this answer changed before it completed. "
                "Please run the request again to use the bot’s current sources."
            )
            summary = (
                "A cited knowledge source was removed or changed before this answer completed; "
                "the generated response was suppressed."
            )
            citations = []
            outcomes = None
            usage = None
            model_name = None
        else:
            draft = guarded.text
            label = "Reply draft" if row.kind == "reply_draft" else "Playground answer"
            summary = (
                "Generated answer failed knowledge grounding checks; a safe fallback was used."
                if not guarded.accepted else
                f"{label} generated using {len(guarded.citations)} knowledge source(s)."
            )
            citations = guarded.citations
            outcomes = guarded.outcomes
            usage = guarded.usage
            model_name = guarded.model_name
        row.status = "succeeded"
        row.integration_context_encrypted = None
        row.playground_history = None
        row.draft = draft
        row.safe_summary = summary
        row.citations = citations
        if outcomes is not None:
            row.tool_outcomes = outcomes
        if usage is not None:
            row.usage = usage
        if model_name is not None:
            row.model_name = model_name
        row.error_code = None
        row.completed_at = completed_at
        await db.commit()
