"""Storefront widget feature routers and shared implementation exports."""

from fastapi import APIRouter

from app.features.widgets.cancellation import router as cancellation_router
from app.features.widgets.management import management_router
from app.features.widgets.order_actions import router as order_actions_router
from app.features.widgets.public_chat import router as public_chat_router
from app.features.widgets.reply_stream import router as reply_stream_router

public_router = APIRouter()
public_router.include_router(public_chat_router)
public_router.include_router(reply_stream_router)
public_router.include_router(order_actions_router)
public_router.include_router(cancellation_router)

__all__ = ["management_router", "public_router"]
