"""Tenant-scoped, read-only knowledge tool adapter.

The caller supplies trusted organization and agent IDs. The model supplies
only the search query; it cannot choose a tenant, bot, or source collection.
"""

from collections.abc import Callable
from uuid import UUID

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.conversation_tool_contracts import (
    ToolName,
    ToolRequest,
    ToolResult,
)
from app.features.ai.application.retrieval_search import search_agent_knowledge


def build_knowledge_search_adapter(
    *,
    organization_id: UUID,
    ai_agent_id: UUID,
) -> Callable:
    async def search(request: ToolRequest) -> ToolResult:
        if request.name != ToolName.KNOWLEDGE_SEARCH:
            raise ValueError("Knowledge adapter received a different tool")
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            result = await search_agent_knowledge(
                db,
                organization_id=organization_id,
                ai_agent_id=ai_agent_id,
                search_text=request.query,
                limit=6,
            )
            matches = result.matches
            return ToolResult(
                name=ToolName.KNOWLEDGE_SEARCH,
                status="ok" if matches else "not_found",
                facts=[match.excerpt[:1200] for match in matches],
                source_ids=[str(match.document_id) for match in matches],
            )

    return search
