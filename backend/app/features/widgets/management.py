"""Tenant-managed storefront widget settings endpoints."""

"""Public, narrowly scoped Shopify storefront chat and tenant widget settings."""

import logging
import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.features.ai.application.defaults import get_default_agent
from app.services.widget_ai import resolve_widget_agent
from app.models import (
    AIAgent,
    Conversation,
    Message,
    SupportWidget,
    SupportWidgetAIAgent,
    User,
)
from app.schemas.widget import (
    WidgetConfigCreate,
    WidgetConfigOut,
    WidgetConfigUpdate,
    WidgetRoutingPreviewIn,
    WidgetRoutingPreviewOut,
)

logger = logging.getLogger(__name__)
VISITOR_SESSION_TTL = timedelta(hours=24)
IDEMPOTENCY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
MAX_HISTORY = 100

management_router = APIRouter(prefix="/integrations/widget", tags=["Storefront chat widget"])
from app.features.widgets.shared import normalized_origins, widget_out


@management_router.get("", response_model=WidgetConfigOut | None)
async def get_widget_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WidgetConfigOut | None:
    widget = await db.scalar(
        select(SupportWidget)
        .where(SupportWidget.organization_id == user.organization_id)
        .order_by(SupportWidget.created_at.asc())
        .limit(1)
    )
    return await _widget_out(db, widget) if widget else None


@management_router.post("/routing-preview", response_model=WidgetRoutingPreviewOut)
async def preview_widget_routing(
    data: WidgetRoutingPreviewIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WidgetRoutingPreviewOut:
    """Preview which of the selected active bots would receive a widget message."""
    widget = await db.scalar(
        select(SupportWidget)
        .where(SupportWidget.organization_id == user.organization_id)
        .order_by(SupportWidget.created_at.asc())
        .limit(1)
    )
    if widget is None:
        raise HTTPException(status_code=404, detail="Create a storefront widget before previewing bot routing")
    selected_ids = list(dict.fromkeys(data.ai_agent_ids))
    agents = list(
        await db.scalars(
            select(AIAgent).where(
                AIAgent.organization_id == user.organization_id,
                AIAgent.id.in_(selected_ids),
                AIAgent.status == "active",
            )
        )
    )
    agent_by_id = {agent.id: agent for agent in agents}
    if len(agent_by_id) != len(selected_ids):
        raise HTTPException(status_code=422, detail="Preview bots must be active bots in this workspace")
    selected_agents = [agent_by_id[agent_id] for agent_id in selected_ids]
    selected = await resolve_widget_agent(
        db,
        widget,
        data.message,
        configured_agent_ids=selected_ids,
        primary_agent_id=selected_agents[0].id,
    )
    if selected is None:
        raise HTTPException(status_code=409, detail="No selected bot is available to handle widget messages")
    return WidgetRoutingPreviewOut(
        ai_agent_id=selected.id,
        ai_agent_name=selected.name,
        configured_bot_count=len(selected_ids),
    )


@management_router.post("", response_model=WidgetConfigOut, status_code=status.HTTP_201_CREATED)
async def create_widget_config(
    data: WidgetConfigCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WidgetConfigOut:
    existing = await db.scalar(
        select(SupportWidget.id)
        .where(SupportWidget.organization_id == user.organization_id)
        .limit(1)
    )
    if existing:
        raise HTTPException(
            status_code=409, detail="A storefront widget already exists for this workspace"
        )
    agents = await _resolve_agents(
        db,
        user.organization_id,
        data.ai_agent_ids or ([data.ai_agent_id] if data.ai_agent_id else None),
    )
    agent = agents[0]
    widget = SupportWidget(
        organization_id=user.organization_id,
        public_id=secrets.token_urlsafe(24),
        ai_agent_id=agent.id,
        allowed_origins=normalized_origins(data.allowed_origins),
        collect_contact=data.collect_contact,
        ai_enabled=data.ai_enabled,
        ai_reply_mode=data.ai_reply_mode,
        enabled=True,
    )
    db.add(widget)
    try:
        await db.flush()
        db.add_all(
            SupportWidgetAIAgent(
                organization_id=user.organization_id,
                widget_id=widget.id,
                ai_agent_id=selected.id,
            )
            for selected in agents
        )
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A storefront widget already exists for this workspace"
        ) from exc
    return await _widget_out(db, widget)


@management_router.put("", response_model=WidgetConfigOut)
async def update_widget_config(
    data: WidgetConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> WidgetConfigOut:
    widget = await db.scalar(
        select(SupportWidget)
        .where(SupportWidget.organization_id == user.organization_id)
        .order_by(SupportWidget.created_at.asc())
        .limit(1)
        .with_for_update()
    )
    if widget is None:
        raise HTTPException(status_code=404, detail="Create a storefront widget first")
    widget.allowed_origins = normalized_origins(data.allowed_origins)
    widget.enabled = data.enabled
    widget.collect_contact = data.collect_contact
    widget.ai_enabled = data.ai_enabled
    widget.ai_reply_mode = data.ai_reply_mode
    if data.ai_agent_ids is not None or data.ai_agent_id is not None:
        requested_ids = data.ai_agent_ids or ([data.ai_agent_id] if data.ai_agent_id else None)
        if requested_ids is None:
            raise HTTPException(status_code=422, detail="Select at least one active AI bot")
        agents = await _resolve_agents(db, user.organization_id, requested_ids)
        await db.execute(
            delete(SupportWidgetAIAgent).where(
                SupportWidgetAIAgent.organization_id == user.organization_id,
                SupportWidgetAIAgent.widget_id == widget.id,
            )
        )
        db.add_all(
            SupportWidgetAIAgent(
                organization_id=user.organization_id,
                widget_id=widget.id,
                ai_agent_id=agent.id,
            )
            for agent in agents
        )
        widget.ai_agent_id = agents[0].id
    await db.flush()
    return await _widget_out(db, widget)


async def _resolve_agents(db: AsyncSession, organization_id, agent_ids):
    if agent_ids is None:
        return [await get_default_agent(db, organization_id)]
    unique_ids = list(dict.fromkeys(agent_ids))
    if not unique_ids:
        raise HTTPException(status_code=422, detail="Select at least one active AI bot")
    agents = list(
        await db.scalars(
            select(AIAgent).where(
                AIAgent.id.in_(unique_ids),
                AIAgent.organization_id == organization_id,
            )
        )
    )
    by_id = {agent.id: agent for agent in agents}
    if len(by_id) != len(unique_ids):
        raise HTTPException(
            status_code=404,
            detail="Every selected bot must belong to this workspace",
        )
    if any(agent.status != "active" for agent in agents):
        raise HTTPException(status_code=409, detail="Every selected bot must be active")
    return [by_id[agent_id] for agent_id in unique_ids]


async def _widget_out(db: AsyncSession, widget: SupportWidget) -> WidgetConfigOut:
    agent_ids = list(
        await db.scalars(
            select(SupportWidgetAIAgent.ai_agent_id)
            .where(
                SupportWidgetAIAgent.organization_id == widget.organization_id,
                SupportWidgetAIAgent.widget_id == widget.id,
            )
            .order_by(SupportWidgetAIAgent.ai_agent_id)
        )
    )
    selected_ids = agent_ids or [widget.ai_agent_id]
    ordered_ids = [widget.ai_agent_id, *(agent_id for agent_id in selected_ids if agent_id != widget.ai_agent_id)]
    last_customer_message_at = await db.scalar(
        select(func.max(Message.created_at))
        .join(
            Conversation,
            (Conversation.organization_id == Message.organization_id)
            & (Conversation.id == Message.conversation_id),
        )
        .where(
            Message.organization_id == widget.organization_id,
            Message.sender_type == "customer",
            Conversation.channel == "shopify_widget",
        )
    )
    return widget_out(widget, ordered_ids, last_customer_message_at)

