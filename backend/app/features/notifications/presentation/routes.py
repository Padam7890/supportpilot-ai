"""Authenticated notification APIs and recipient-scoped live updates."""

import asyncio
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.features.notifications.application.events import EVENT_TYPES
from app.features.notifications.infrastructure.repository import NotificationRepository
from app.features.notifications.presentation.schemas import (
    NotificationListResponse,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    NotificationUnreadCountResponse,
    ReadAllResponse,
)
from app.models import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["Notifications"])
MAX_STREAM_LIFETIME = timedelta(minutes=30)


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(default=30, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=256),
    category: str | None = Query(default=None, pattern=r"^(inbox|ai|automation|integration|knowledge|team|system)$"),
    unread_only: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        items, next_cursor, has_more = await NotificationRepository(db).list_for_user(
            user.organization_id, user.id, limit=limit, cursor=cursor,
            category=category, unread_only=unread_only,
        )
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid notification cursor") from None
    return {"items": items, "next_cursor": next_cursor, "has_more": has_more}


@router.get("/unread-count", response_model=NotificationUnreadCountResponse)
async def unread_count(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    count = await NotificationRepository(db).unread_count(user.organization_id, user.id)
    return {"unread_count": count}


@router.patch("/{notification_id}/read", status_code=204)
async def mark_notification_read(notification_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    changed = await NotificationRepository(db).mark_read(user.organization_id, user.id, notification_id)
    if not changed:
        raise HTTPException(status_code=404, detail="Notification not found")


@router.post("/read-all", response_model=ReadAllResponse)
async def mark_all_notifications_read(category: str | None = Query(default=None, pattern=r"^(inbox|ai|automation|integration|knowledge|team|system)$"), db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    count = await NotificationRepository(db).mark_all_read(user.organization_id, user.id, category)
    return {"affected_count": count}


@router.patch("/{notification_id}/dismiss", status_code=204)
async def dismiss_notification(notification_id: UUID, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    changed = await NotificationRepository(db).dismiss(user.organization_id, user.id, notification_id)
    if not changed:
        raise HTTPException(status_code=404, detail="Notification not found")


@router.get("/preferences", response_model=list[NotificationPreferenceResponse])
async def get_notification_preferences(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    return await NotificationRepository(db).get_preferences(user.organization_id, user.id)


@router.patch("/preferences/{event_type}", response_model=NotificationPreferenceResponse)
async def update_notification_preference(
    event_type: str,
    payload: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if event_type not in EVENT_TYPES:
        raise HTTPException(status_code=404, detail="Notification preference not found")
    if payload.email_enabled is True and not (settings.email_smtp_host and settings.email_from_address):
        raise HTTPException(status_code=503, detail="Email notifications are not configured")
    row = await NotificationRepository(db).update_preference(
        user.organization_id, user.id, event_type,
        in_app_enabled=payload.in_app_enabled, email_enabled=payload.email_enabled,
    )
    return {"event_type": row.event_type, "in_app_enabled": row.in_app_enabled, "email_enabled": row.email_enabled}


async def _notification_events(request: Request, channel: str) -> AsyncIterator[str]:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return
    pubsub = redis.pubsub()
    await pubsub.subscribe(channel)
    expires_at = datetime.now(UTC) + MAX_STREAM_LIFETIME
    try:
        yield "retry: 5000\n\n"
        while datetime.now(UTC) < expires_at and not await request.is_disconnected():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
            if message and message.get("data"):
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8", errors="ignore")
                yield f"event: notification\ndata: {data}\n\n"
            else:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0)
        # Ask EventSource to reconnect after releasing Redis resources.
        yield ": reconnect\n\n"
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.aclose()


@router.get("/stream")
async def notification_stream(request: Request, user: User = Depends(get_current_user)):
    if getattr(request.app.state, "redis", None) is None:
        raise HTTPException(status_code=503, detail="Live notifications are unavailable")
    channel = f"supportpilot:notifications:{user.organization_id}:{user.id}"
    logger.info(
        "notification_stream_opened",
        extra={
            "organization_id": str(user.organization_id),
            "user_id": str(user.id),
        },
    )
    return StreamingResponse(_notification_events(request, channel), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})
