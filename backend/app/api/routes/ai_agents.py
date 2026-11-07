from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.features.ai.application.agent_audit import record_agent_audit
from app.models import (
    AIAgent,
    AIAgentAudit,
    AIAgentKnowledgeBase,
    KnowledgeBase,
    SupportWidgetAIAgent,
    User,
)
from app.schemas.ai_agents import (
    AIAgentAuditOut,
    AIAgentAuditPage,
    AIAgentCreate,
    AIAgentKnowledgeBasesUpdate,
    AIAgentOut,
    AIAgentPage,
    AIAgentUpdate,
)
from app.schemas.errors import COMMON_ERROR_RESPONSES

router = APIRouter(prefix="/ai/agents", tags=["AI agents"], responses=COMMON_ERROR_RESPONSES)


def serialize_agent(
    agent: AIAgent,
    base_ids: list[UUID],
    *,
    include_instructions: bool = True,
) -> AIAgentOut:
    return AIAgentOut(
        id=agent.id,
        name=agent.name,
        system_instructions=agent.system_instructions if include_instructions else "",
        status=agent.status,
        config_version=agent.config_version,
        is_default=agent.is_default,
        allowed_tools=agent.allowed_tools,
        knowledge_base_ids=base_ids,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
    )


async def agent_out(db: AsyncSession, agent: AIAgent) -> AIAgentOut:
    base_ids = list(await db.scalars(
        select(AIAgentKnowledgeBase.knowledge_base_id)
        .where(
            AIAgentKnowledgeBase.organization_id == agent.organization_id,
            AIAgentKnowledgeBase.ai_agent_id == agent.id,
        )
        .order_by(AIAgentKnowledgeBase.knowledge_base_id)
    ))
    return serialize_agent(agent, base_ids)


async def agent_page_out(
    db: AsyncSession,
    agents: list[AIAgent],
    *,
    include_instructions: bool = True,
) -> list[AIAgentOut]:
    if not agents:
        return []

    assignments = await db.execute(
        select(AIAgentKnowledgeBase.ai_agent_id, AIAgentKnowledgeBase.knowledge_base_id)
        .where(
            AIAgentKnowledgeBase.organization_id == agents[0].organization_id,
            AIAgentKnowledgeBase.ai_agent_id.in_([agent.id for agent in agents]),
        )
        .order_by(AIAgentKnowledgeBase.ai_agent_id, AIAgentKnowledgeBase.knowledge_base_id)
    )
    base_ids_by_agent: dict[UUID, list[UUID]] = {}
    for agent_id, base_id in assignments:
        base_ids_by_agent.setdefault(agent_id, []).append(base_id)
    return [
        serialize_agent(
            agent,
            base_ids_by_agent.get(agent.id, []),
            include_instructions=include_instructions,
        )
        for agent in agents
    ]


@router.get("", response_model=AIAgentPage)
async def list_agents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AIAgentPage:
    predicate = AIAgent.organization_id == user.organization_id
    total = await db.scalar(select(func.count()).select_from(AIAgent).where(predicate)) or 0
    agents = list(await db.scalars(
        select(AIAgent).where(predicate).order_by(AIAgent.is_default.desc(), AIAgent.created_at, AIAgent.id).limit(limit).offset(offset)
    ))
    return AIAgentPage(
        items=await agent_page_out(
            db,
            agents,
            include_instructions=user.role in {"owner", "admin"},
        ),
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=AIAgentOut, status_code=201)
async def create_agent(
    data: AIAgentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AIAgentOut:
    requested = list(dict.fromkeys(data.knowledge_base_ids))
    bases = list(await db.scalars(select(KnowledgeBase).where(
        KnowledgeBase.organization_id == user.organization_id,
        KnowledgeBase.id.in_(requested) if requested else False,
    ).order_by(KnowledgeBase.id).with_for_update()))
    if len(bases) != len(requested):
        raise HTTPException(status_code=422, detail="Every assigned knowledge base must belong to this workspace")
    if any(base.status != "active" for base in bases):
        raise HTTPException(status_code=422, detail="Archived knowledge bases cannot be newly assigned")
    agent = AIAgent(
        organization_id=user.organization_id,
        name=data.name.strip(),
        system_instructions=data.system_instructions.strip(),
        allowed_tools=list(data.allowed_tools),
    )
    db.add(agent)
    await db.flush()
    db.add_all(AIAgentKnowledgeBase(
        organization_id=user.organization_id, ai_agent_id=agent.id, knowledge_base_id=base.id
    ) for base in bases)
    record_agent_audit(
        db,
        agent=agent,
        actor_id=user.id,
        event_type="created",
        details={
            "name": agent.name,
            "knowledge_base_ids": sorted(str(base.id) for base in bases),
            "allowed_tools": agent.allowed_tools,
        },
    )
    await db.flush()
    return await agent_out(db, agent)


@router.get("/{agent_id}", response_model=AIAgentOut)
async def get_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AIAgentOut:
    agent = await _get_agent(db, user.organization_id, agent_id)
    result = await agent_out(db, agent)
    if user.role not in {"owner", "admin"}:
        result.system_instructions = ""
    return result


@router.get("/{agent_id}/audit", response_model=AIAgentAuditPage)
async def list_agent_audit(
    agent_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AIAgentAuditPage:
    await _get_agent(db, user.organization_id, agent_id)
    predicate = (
        AIAgentAudit.organization_id == user.organization_id,
        AIAgentAudit.ai_agent_id == agent_id,
    )
    total = await db.scalar(
        select(func.count()).select_from(AIAgentAudit).where(*predicate)
    ) or 0
    rows = await db.execute(
        select(AIAgentAudit, User.full_name)
        .join(
            User,
            (User.organization_id == AIAgentAudit.organization_id)
            & (User.id == AIAgentAudit.actor_user_id),
        )
        .where(*predicate)
        .order_by(AIAgentAudit.created_at.desc(), AIAgentAudit.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return AIAgentAuditPage(
        items=[
            AIAgentAuditOut(
                id=audit.id,
                ai_agent_id=audit.ai_agent_id,
                actor_user_id=audit.actor_user_id,
                actor_name=actor_name,
                event_type=audit.event_type,
                config_version=audit.config_version,
                details=audit.details,
                created_at=audit.created_at,
            )
            for audit, actor_name in rows.all()
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.put("/{agent_id}", response_model=AIAgentOut)
async def update_agent(
    agent_id: UUID,
    data: AIAgentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AIAgentOut:
    agent = await _get_agent(db, user.organization_id, agent_id, lock=True)
    previous_name = agent.name
    previous_instructions = agent.system_instructions
    previous_tools = list(agent.allowed_tools or [])
    new_name = data.name.strip()
    new_instructions = data.system_instructions.strip()
    new_tools = list(data.allowed_tools) if data.allowed_tools is not None else previous_tools
    changed_fields = []
    if previous_name != new_name:
        changed_fields.append("name")
    if previous_instructions != new_instructions:
        changed_fields.append("system_instructions")
    if previous_tools != new_tools:
        changed_fields.append("allowed_tools")
    requested_bases: list[KnowledgeBase] | None = None
    previous_base_ids: list[UUID] = []
    normalized_previous: list[str] = []
    normalized_requested: list[str] = []
    if data.knowledge_base_ids is not None:
        previous_base_ids = list(await db.scalars(
            select(AIAgentKnowledgeBase.knowledge_base_id)
            .where(
                AIAgentKnowledgeBase.organization_id == user.organization_id,
                AIAgentKnowledgeBase.ai_agent_id == agent.id,
            )
            .order_by(AIAgentKnowledgeBase.knowledge_base_id)
        ))
        requested_ids = list(dict.fromkeys(data.knowledge_base_ids))
        requested_bases = list(await db.scalars(select(KnowledgeBase).where(
            KnowledgeBase.organization_id == user.organization_id,
            KnowledgeBase.id.in_(requested_ids) if requested_ids else False,
        ).order_by(KnowledgeBase.id).with_for_update()))
        if len(requested_bases) != len(requested_ids):
            raise HTTPException(status_code=422, detail="Every assigned knowledge base must belong to this workspace")
        previously_assigned = set(previous_base_ids)
        if any(base.status != "active" and base.id not in previously_assigned for base in requested_bases):
            raise HTTPException(status_code=422, detail="Archived knowledge bases cannot be newly assigned")
        normalized_previous = sorted(str(value) for value in previous_base_ids)
        normalized_requested = sorted(str(value) for value in requested_ids)
        if normalized_previous != normalized_requested:
            changed_fields.append("knowledge_base_ids")
    if changed_fields:
        agent.name = new_name
        agent.system_instructions = new_instructions
        agent.allowed_tools = new_tools
        if requested_bases is not None and "knowledge_base_ids" in changed_fields:
            await db.execute(delete(AIAgentKnowledgeBase).where(
                AIAgentKnowledgeBase.organization_id == user.organization_id,
                AIAgentKnowledgeBase.ai_agent_id == agent.id,
            ))
            db.add_all(AIAgentKnowledgeBase(
                organization_id=user.organization_id,
                ai_agent_id=agent.id,
                knowledge_base_id=base.id,
            ) for base in requested_bases)
        agent.config_version += 1
        record_agent_audit(
            db,
            agent=agent,
            actor_id=user.id,
            event_type="updated",
            details={
                "changed_fields": changed_fields,
                "previous_name": previous_name if "name" in changed_fields else None,
                "name": new_name if "name" in changed_fields else None,
                "system_instructions_changed": "system_instructions" in changed_fields,
                "previous_allowed_tools": previous_tools if "allowed_tools" in changed_fields else None,
                "allowed_tools": new_tools if "allowed_tools" in changed_fields else None,
                "previous_knowledge_base_ids": normalized_previous if "knowledge_base_ids" in changed_fields else None,
                "knowledge_base_ids": normalized_requested if "knowledge_base_ids" in changed_fields else None,
            },
        )
        await db.flush()
    return await agent_out(db, agent)


@router.put("/{agent_id}/knowledge-bases", response_model=AIAgentOut)
async def replace_agent_knowledge_bases(
    agent_id: UUID,
    data: AIAgentKnowledgeBasesUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AIAgentOut:
    agent = await _get_agent(db, user.organization_id, agent_id, lock=True)
    previous_base_ids = list(await db.scalars(
        select(AIAgentKnowledgeBase.knowledge_base_id)
        .where(
            AIAgentKnowledgeBase.organization_id == user.organization_id,
            AIAgentKnowledgeBase.ai_agent_id == agent.id,
        )
        .order_by(AIAgentKnowledgeBase.knowledge_base_id)
    ))
    requested = list(dict.fromkeys(data.knowledge_base_ids))
    bases = list(await db.scalars(select(KnowledgeBase).where(
        KnowledgeBase.organization_id == user.organization_id,
        KnowledgeBase.id.in_(requested) if requested else False,
    ).order_by(KnowledgeBase.id).with_for_update()))
    if len(bases) != len(requested):
        raise HTTPException(status_code=422, detail="Every assigned knowledge base must belong to this workspace")
    previously_assigned = set(previous_base_ids)
    newly_archived = [
        base.id for base in bases
        if base.status != "active" and base.id not in previously_assigned
    ]
    if newly_archived:
        raise HTTPException(status_code=422, detail="Archived knowledge bases cannot be newly assigned")
    normalized_previous = sorted(str(value) for value in previous_base_ids)
    normalized_requested = sorted(str(value) for value in requested)
    if normalized_previous == normalized_requested:
        return await agent_out(db, agent)
    await db.execute(delete(AIAgentKnowledgeBase).where(
        AIAgentKnowledgeBase.organization_id == user.organization_id,
        AIAgentKnowledgeBase.ai_agent_id == agent.id,
    ))
    db.add_all(AIAgentKnowledgeBase(
        organization_id=user.organization_id, ai_agent_id=agent.id, knowledge_base_id=base.id
    ) for base in bases)
    agent.config_version += 1
    record_agent_audit(
        db,
        agent=agent,
        actor_id=user.id,
        event_type="knowledge_bases_changed",
        details={
            "previous_knowledge_base_ids": normalized_previous,
            "knowledge_base_ids": normalized_requested,
        },
    )
    await db.flush()
    return await agent_out(db, agent)


@router.post("/{agent_id}/activate", response_model=AIAgentOut)
async def activate_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AIAgentOut:
    agent = await _get_agent(db, user.organization_id, agent_id, lock=True)
    if agent.status != "active":
        agent.status = "active"
        agent.config_version += 1
        record_agent_audit(
            db,
            agent=agent,
            actor_id=user.id,
            event_type="activated",
            details={"status": "active"},
        )
        await db.flush()
    return await agent_out(db, agent)


@router.post("/{agent_id}/make-default", response_model=AIAgentOut)
async def make_agent_default(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AIAgentOut:
    agents = list(
        await db.scalars(
            select(AIAgent)
            .where(AIAgent.organization_id == user.organization_id)
            .order_by(AIAgent.id)
            .with_for_update()
        )
    )
    selected = next((agent for agent in agents if agent.id == agent_id), None)
    if selected is None:
        raise HTTPException(status_code=404, detail="AI agent not found")
    if selected.status != "active":
        raise HTTPException(status_code=409, detail="Only an active AI bot can be the workspace default")
    previous = next((agent for agent in agents if agent.is_default), None)
    if previous is not None and previous.id == selected.id:
        return await agent_out(db, selected)

    if previous is not None:
        previous.is_default = False
        previous.config_version += 1
        record_agent_audit(
            db,
            agent=previous,
            actor_id=user.id,
            event_type="updated",
            details={
                "changed_fields": ["is_default"],
                "is_default": False,
                "default_agent_id": str(selected.id),
            },
        )
        await db.flush()

    selected.is_default = True
    selected.config_version += 1
    record_agent_audit(
        db,
        agent=selected,
        actor_id=user.id,
        event_type="updated",
        details={
            "changed_fields": ["is_default"],
            "is_default": True,
            "previous_default_agent_id": str(previous.id) if previous else None,
        },
    )
    await db.flush()
    return await agent_out(db, selected)


@router.post("/{agent_id}/deactivate", response_model=AIAgentOut)
async def deactivate_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> AIAgentOut:
    agent = await _get_agent(db, user.organization_id, agent_id, lock=True)
    if agent.is_default:
        raise HTTPException(status_code=409, detail="The default AI agent cannot be deactivated")
    assigned_to_widget = await db.scalar(
        select(SupportWidgetAIAgent.widget_id).where(
            SupportWidgetAIAgent.organization_id == user.organization_id,
            SupportWidgetAIAgent.ai_agent_id == agent.id,
        ).limit(1)
    )
    if assigned_to_widget is not None:
        raise HTTPException(
            status_code=409,
            detail="Remove this bot from the storefront widget before deactivating it",
        )
    if agent.status != "inactive":
        agent.status = "inactive"
        agent.config_version += 1
        record_agent_audit(
            db,
            agent=agent,
            actor_id=user.id,
            event_type="deactivated",
            details={"status": "inactive"},
        )
        await db.flush()
    return await agent_out(db, agent)


async def _get_agent(db: AsyncSession, organization_id: UUID, agent_id: UUID, *, lock: bool = False) -> AIAgent:
    statement = select(AIAgent).where(AIAgent.id == agent_id, AIAgent.organization_id == organization_id)
    if lock:
        statement = statement.with_for_update()
    agent = await db.scalar(statement)
    if agent is None:
        raise HTTPException(status_code=404, detail="AI agent not found")
    return agent
