import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from redis.asyncio import Redis

from app.api.router import api_router
from app.core.config import settings
from app.core.database import check_database, close_database
from app.schemas.errors import ProblemDetails

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

_default_openapi = app.openapi


def custom_openapi() -> dict[str, object]:
    schema = _default_openapi()
    schema.setdefault("components", {}).setdefault("schemas", {})["ProblemDetails"] = (
        ProblemDetails.model_json_schema()
    )
    return schema


app.openapi = custom_openapi  # type: ignore[method-assign]


def problem_response(
    request: Request,
    status_code: int,
    detail: str,
    code: str,
    *,
    extra: dict[str, object] | None = None,
) -> JSONResponse:
    try:
        title = HTTPStatus(status_code).phrase
    except ValueError:
        title = "Application error"
    problem = ProblemDetails(
        type=f"urn:supportpilot:problem:{code}",
        title=title,
        status=status_code,
        detail=detail,
        instance=request.url.path,
        code=code,
    ).model_dump(exclude_none=True)
    if extra:
        problem.update(extra)
    return JSONResponse(
        status_code=status_code,
        content=problem,
        media_type="application/problem+json",
    )


def error_code(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        415: "unsupported_media_type",
        422: "validation_error",
        429: "too_many_requests",
    }.get(status_code, "internal_error" if status_code >= 500 else "http_error")


@app.exception_handler(HTTPException)
async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "The request could not be completed"
    return problem_response(request, exc.status_code, detail, error_code(exc.status_code))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = [
        {"loc": list(error["loc"]), "msg": error["msg"], "type": error["type"]}
        for error in exc.errors()
    ]
    return problem_response(
        request,
        422,
        "Request validation failed",
        "validation_error",
        extra={"errors": errors},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled API error", exc_info=exc)
    return problem_response(
        request,
        500,
        "An unexpected server error occurred",
        "internal_error",
    )

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
