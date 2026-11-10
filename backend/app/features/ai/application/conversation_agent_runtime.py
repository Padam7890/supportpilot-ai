"""Composition root for the standalone read-only conversation agent.

The caller must supply server-authenticated tenant and bot identifiers. This
module is intentionally not invoked from the live execution worker yet.
"""

from uuid import UUID

from app.features.ai.application.conversation_agent import (
    AgentRunResult, run_conversation_agent,
)
from app.features.ai.application.conversation_agent_planner import plan_agent_turn
from app.features.ai.application.conversation_agent_contracts import AgentInput
from app.features.ai.application.conversation_catalog_adapter import (
    build_catalog_search_adapter,
)
from app.features.ai.application.conversation_knowledge_adapter import (
    build_knowledge_search_adapter,
)
from app.features.ai.application.conversation_tool_contracts import ToolName


async def run_read_only_agent_turn(
    *,
    organization_id: UUID,
    ai_agent_id: UUID,
    agent_input: AgentInput,
    allowed_tools: frozenset[ToolName] = frozenset(),
) -> AgentRunResult:
    """Compose tenant-scoped adapters; do not accept IDs from model output."""
    return await run_conversation_agent(
        agent_input,
        planner=plan_agent_turn,
        allowed_tools=allowed_tools,
        adapters={
            ToolName.KNOWLEDGE_SEARCH: build_knowledge_search_adapter(
                organization_id=organization_id,
                ai_agent_id=ai_agent_id,
            ),
            ToolName.CATALOG_SEARCH: build_catalog_search_adapter(
                organization_id=organization_id,
            ),
        },
    )
