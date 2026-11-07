from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIAgent, AIAgentKnowledgeBase, KnowledgeBase


async def create_workspace_ai_defaults(db: AsyncSession, organization_id: UUID) -> AIAgent:
    """Create the compatibility base and bot for a newly registered workspace."""
    base = KnowledgeBase(
        organization_id=organization_id,
        name="General",
        description="Default knowledge base for workspace content",
        status="active",
        is_default=True,
    )
    agent = AIAgent(
        organization_id=organization_id,
        name="SupportPilot Assistant",
        system_instructions="",
        allowed_tools=["recommend_products", "compare_products"],
        status="active",
        config_version=1,
        is_default=True,
    )
    db.add_all([base, agent])
    await db.flush()
    db.add(AIAgentKnowledgeBase(
        organization_id=organization_id,
        ai_agent_id=agent.id,
        knowledge_base_id=base.id,
    ))
    await db.flush()
    return agent


async def get_default_agent(db: AsyncSession, organization_id: UUID) -> AIAgent:
    agent = await db.scalar(select(AIAgent).where(
        AIAgent.organization_id == organization_id,
        AIAgent.is_default.is_(True),
    ))
    if agent is None:
        raise RuntimeError("Workspace AI defaults are unavailable; apply the latest database migration")
    return agent
