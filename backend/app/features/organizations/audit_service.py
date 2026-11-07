"""Tenant-scoped, privacy-minimized workspace audit history."""

from uuid import UUID

from sqlalchemy import func, literal, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AIAgentAudit,
    CommerceActionAudit,
    IntegrationConnectionAudit,
    KnowledgeBaseAudit,
    TeamAudit,
    TicketActivity,
    User,
)
from app.schemas.workspace_audit import WorkspaceAuditItem, WorkspaceAuditPage


def _event_query(
    model,
    *,
    organization_id: UUID,
    category: str,
    target_id,
    event_type,
):
    return select(
        model.id.label("id"),
        literal(category).label("category"),
        target_id.label("target_id"),
        event_type.label("event_type"),
        model.actor_user_id.label("actor_user_id"),
        model.created_at.label("created_at"),
    ).where(model.organization_id == organization_id)


async def list_workspace_audit(
    db: AsyncSession,
    *,
    organization_id: UUID,
    limit: int,
    offset: int,
) -> WorkspaceAuditPage:
    """Return recent audit metadata without exposing arbitrary audit details."""
    events = union_all(
        _event_query(
            AIAgentAudit,
            organization_id=organization_id,
            category="AI bot",
            target_id=AIAgentAudit.ai_agent_id,
            event_type=AIAgentAudit.event_type,
        ),
        _event_query(
            KnowledgeBaseAudit,
            organization_id=organization_id,
            category="Knowledge",
            target_id=KnowledgeBaseAudit.knowledge_base_id,
            event_type=KnowledgeBaseAudit.event_type,
        ),
        _event_query(
            TeamAudit,
            organization_id=organization_id,
            category="Team",
            target_id=TeamAudit.team_id,
            event_type=TeamAudit.event_type,
        ),
        _event_query(
            IntegrationConnectionAudit,
            organization_id=organization_id,
            category="Integration",
            target_id=IntegrationConnectionAudit.connection_id,
            event_type=IntegrationConnectionAudit.event_type,
        ),
        _event_query(
            CommerceActionAudit,
            organization_id=organization_id,
            category="Commerce",
            target_id=CommerceActionAudit.commerce_action_id,
            event_type=CommerceActionAudit.event_type,
        ),
        _event_query(
            TicketActivity,
            organization_id=organization_id,
            category="Ticket",
            target_id=TicketActivity.ticket_id,
            event_type=TicketActivity.activity_type,
        ),
    ).subquery("workspace_audit_events")

    total = int(await db.scalar(select(func.count()).select_from(events)) or 0)
    rows = await db.execute(
        select(
            events.c.id,
            events.c.category,
            events.c.target_id,
            events.c.event_type,
            func.coalesce(User.full_name, literal("System")).label("actor_name"),
            events.c.created_at,
        )
        .outerjoin(
            User,
            (User.organization_id == organization_id)
            & (User.id == events.c.actor_user_id),
        )
        .order_by(events.c.created_at.desc(), events.c.id.desc())
        .limit(limit)
        .offset(offset)
    )
    items = [WorkspaceAuditItem.model_validate(row._mapping) for row in rows]
    return WorkspaceAuditPage(items=items, total=total, limit=limit, offset=offset)
