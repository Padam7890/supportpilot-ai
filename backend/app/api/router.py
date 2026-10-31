from fastapi import APIRouter

from app.api.routes import auth, conversations, customers, platform, tickets, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(customers.router)
api_router.include_router(tickets.router)
api_router.include_router(conversations.router)
api_router.include_router(users.router)
api_router.include_router(platform.router)
