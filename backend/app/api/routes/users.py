"""Compatibility router combining team and organization settings endpoints."""

from fastapi import APIRouter

from app.features.organizations.router import router as organizations_router
from app.features.users import router as users_router

router = APIRouter()
router.include_router(users_router)
router.include_router(organizations_router)

__all__ = ["router"]
