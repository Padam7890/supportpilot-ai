import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.router import api_router
from app.core.config import settings
from app.core.database import check_database, close_database

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logging.basicConfig(level=settings.log_level.upper())
    redis_client = Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    app.state.redis = redis_client
    try:
        yield
    finally:
        await redis_client.aclose()
        await close_database()


app = FastAPI(
    title=settings.app_name,
    description="AI-powered customer support platform",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan,
)
app.include_router(api_router, prefix=settings.api_v1_prefix)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "status": "running",
        "version": "0.1.0",
    }


@app.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness() -> dict[str, object]:
    try:
        await check_database()
        redis_client: Redis = app.state.redis
        await redis_client.ping()
    except Exception:
        logger.exception("Readiness check failed")
        raise HTTPException(
            status_code=503,
            detail="Application dependencies unavailable",
        ) from None

    return {
        "status": "ready",
        "checks": {
            "database": "connected",
            "redis": "connected",
        },
    }
