"""AI execution job adapter."""

from uuid import NAMESPACE_URL, UUID, uuid5

from app.services.ai_worker import claim_ai_execution, process_ai_execution
from app.db.session import SessionLocal, set_tenant_context
from app.features.notifications.application.events import TicketNotificationPayload, enqueue_notification_event
from app.models import AIExecution, Conversation
from sqlalchemy import select
from app.workers.application.contracts import ClaimedJob, JobHandler


class AIExecutionHandler(JobHandler):
    kind = "ai"

    async def claim(self, organization_id: UUID) -> ClaimedJob | None:
        job_id = await claim_ai_execution(organization_id)
        return ClaimedJob(self.kind, organization_id, job_id) if job_id else None

    async def process(self, job: ClaimedJob) -> None:
        assert job.job_id is not None
        await process_ai_execution(job.organization_id, job.job_id)
        async with SessionLocal() as db:
            await set_tenant_context(db, job.organization_id)
            execution = await db.scalar(select(AIExecution).where(
                AIExecution.organization_id == job.organization_id,
                AIExecution.id == job.job_id,
                AIExecution.kind == "widget_reply",
                AIExecution.reply_status == "escalated",
            ))
            if execution is None or execution.conversation_id is None:
                return
            conversation = await db.scalar(select(Conversation).where(
                Conversation.organization_id == job.organization_id,
                Conversation.id == execution.conversation_id,
            ))
            if conversation is None:
                return
            await enqueue_notification_event(
                db,
                organization_id=job.organization_id,
                event_type="ai.escalation_required",
                aggregate_type="ticket",
                aggregate_id=conversation.ticket_id,
                event_id=uuid5(NAMESPACE_URL, f"ai-escalation:{execution.id}"),
                payload=TicketNotificationPayload(
                    ticket_id=conversation.ticket_id,
                    conversation_id=execution.conversation_id,
                ),
            )
            await db.commit()
