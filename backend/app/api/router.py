from fastapi import APIRouter

from app.api.routes import (
    ai,
    catalog,
    commerce_actions,
    integration_management,
    integrations,
    knowledge,
    platform,
    recommendation_settings,
    recommendations,
    search,
    shopify_orders,
)
from app.features.analytics import router as analytics_router
from app.features.auth.router import router as auth_router
from app.features.conversations.router import router as conversations_router
from app.features.customers.router import router as customers_router
from app.features.inbox.router import router as inbox_router
from app.features.organizations.router import router as organizations_router
from app.features.tickets.router import router as tickets_router
from app.features.users import router as users_router
from app.features.widgets import management_router as widget_management_router
from app.features.widgets import public_router as widget_public_router

api_router = APIRouter()
api_router.include_router(analytics_router)
api_router.include_router(ai.router)
api_router.include_router(auth_router)
api_router.include_router(customers_router)
api_router.include_router(tickets_router)
api_router.include_router(conversations_router)
api_router.include_router(commerce_actions.router)
api_router.include_router(catalog.router)
api_router.include_router(catalog.webhook_router)
api_router.include_router(inbox_router)
api_router.include_router(integrations.router)
api_router.include_router(shopify_orders.orders_router)
api_router.include_router(integration_management.router)
api_router.include_router(knowledge.router)
api_router.include_router(users_router)
api_router.include_router(organizations_router)
api_router.include_router(widget_management_router)
api_router.include_router(widget_public_router)
api_router.include_router(platform.router)
api_router.include_router(recommendations.router)
api_router.include_router(recommendation_settings.router)
api_router.include_router(search.router)
