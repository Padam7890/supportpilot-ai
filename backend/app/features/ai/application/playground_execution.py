"""Playground-specific application operations.

The playground is a preview, never a storefront action executor.
Knowledge inventory access and completion remain tenant-scoped.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.knowledge_inventory import (
    format_knowledge_inventory,
    load_knowledge_inventory,
)
from app.models import AIExecution


async def complete_playground_knowledge_inventory(
    organization_id: UUID,
    execution_id: UUID,
    *,
    ai_agent_id: UUID | None,
) -> None:
    """List assigned knowledge without a model call or cross-tenant reads."""
    now = datetime.now(UTC)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        inventory = await load_knowledge_inventory(
            db,
            organization_id=organization_id,
            ai_agent_id=ai_agent_id,
        )
        answer, document_count = format_knowledge_inventory(inventory)
        row = await db.scalar(
            select(AIExecution)
            .where(
                AIExecution.id == execution_id,
                AIExecution.organization_id == organization_id,
                AIExecution.kind == "playground",
                AIExecution.status == "running",
            )
            .with_for_update()
        )
        if row is None:
            await db.rollback()
            return
        row.status = "succeeded"
        row.playground_history = None
        row.integration_context_encrypted = None
        row.draft = answer
        row.safe_summary = (
            f"Listed {document_count} ready document(s) in this bot’s active assigned sources; "
            "no model call was made."
        )
        row.citations = []
        row.tool_outcomes = [{
            "tool": "knowledge_source_inventory",
            "status": "completed",
            "result_count": document_count,
        }]
        row.usage = {}
        row.model_name = None
        row.error_code = None
        row.completed_at = now
        await db.commit()
