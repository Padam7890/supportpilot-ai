"""Team membership and invitation feature router composition."""

from fastapi import APIRouter

from app.features.users.invitations import invitations_router
from app.features.users.router import router as members_router

router = APIRouter()
router.include_router(members_router)
router.include_router(invitations_router)

__all__ = ["router"]
