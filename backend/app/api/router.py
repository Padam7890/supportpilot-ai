from fastapi import APIRouter

from app.api.routes import (
    ai,
    analytics,
    auth,
    commerce_actions,
    conversations,
    customers,
    inbox,
    integrations,
    knowledge,
    platform,
    search,
    tickets,
    users,
    widgets,
)

api_router = APIRouter()
api_router.include_router(analytics.router)
api_router.include_router(ai.router)
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(tickets.router)
api_router.include_router(conversations.router)
api_router.include_router(commerce_actions.router)
api_router.include_router(inbox.router)
api_router.include_router(integrations.router)
api_router.include_router(knowledge.router)
api_router.include_router(users.router)
api_router.include_router(widgets.management_router)
api_router.include_router(widgets.public_router)
api_router.include_router(platform.router)
api_router.include_router(search.router)
