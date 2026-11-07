from fastapi import APIRouter

from app.api.routes import (
    ai,
    ai_agents,
    catalog,
    commerce_actions,
    integration_management,
    integrations,
    knowledge,
    knowledge_bases,
    platform,
    recommendation_settings,
    recommendations,
    search,
    shopify_orders,
)
from app.features.analytics import router as analytics_router
from app.features.attachments import router as attachments_router
from app.features.auth.router import router as auth_router
from app.features.automations.router import router as automations_router
from app.features.conversations.router import router as conversations_router
from app.features.customers.router import router as customers_router
from app.features.inbox.router import router as inbox_router
from app.features.organizations.router import router as organizations_router
from app.features.tickets.router import router as tickets_router
from app.features.teams import router as teams_router
from app.features.users import router as users_router
from app.features.saved_replies import router as saved_replies_router
from app.features.widgets import management_router as widget_management_router
from app.features.widgets import public_router as widget_public_router

api_router = APIRouter()
api_router.include_router(analytics_router)
api_router.include_router(attachments_router)
api_router.include_router(automations_router)
api_router.include_router(ai.router)
api_router.include_router(ai_agents.router)
api_router.include_router(auth_router)
api_router.include_router(customers_router)
api_router.include_router(tickets_router)
api_router.include_router(teams_router)
api_router.include_router(conversations_router)
api_router.include_router(commerce_actions.router)
api_router.include_router(catalog.router)
api_router.include_router(catalog.webhook_router)
api_router.include_router(inbox_router)
api_router.include_router(integrations.router)
api_router.include_router(shopify_orders.orders_router)
api_router.include_router(integration_management.router)
api_router.include_router(knowledge.router)
api_router.include_router(knowledge_bases.router)
api_router.include_router(users_router)
api_router.include_router(saved_replies_router)
api_router.include_router(organizations_router)
api_router.include_router(widget_management_router)
api_router.include_router(widget_public_router)
api_router.include_router(platform.router)
api_router.include_router(recommendations.router)
api_router.include_router(recommendation_settings.router)
api_router.include_router(search.router)
