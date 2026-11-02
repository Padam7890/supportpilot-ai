"""Tenant-managed storefront widget settings endpoints."""

"""Public, narrowly scoped Shopify storefront chat and tenant widget settings."""

import logging
import re
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.models import (
    SupportWidget,
    User,
)
from app.schemas.widget import (
    WidgetConfigCreate,
    WidgetConfigOut,
    WidgetConfigUpdate,
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
    return widget_out(widget) if widget else None


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
    widget = SupportWidget(
        organization_id=user.organization_id,
        public_id=secrets.token_urlsafe(24),
        allowed_origins=normalized_origins(data.allowed_origins),
        collect_contact=data.collect_contact,
        ai_enabled=data.ai_enabled,
        ai_reply_mode=data.ai_reply_mode,
        enabled=True,
    )
    db.add(widget)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409, detail="A storefront widget already exists for this workspace"
        ) from exc
    return widget_out(widget)


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
    await db.flush()
    return widget_out(widget)

