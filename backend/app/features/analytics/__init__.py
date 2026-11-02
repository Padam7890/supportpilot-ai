"""Analytics feature router composition."""

from fastapi import APIRouter

from app.features.analytics.recommendations import recommendations_router
from app.features.analytics.router import router as core_analytics_router

router = APIRouter()
router.include_router(core_analytics_router)
router.include_router(recommendations_router)

__all__ = ["router"]
