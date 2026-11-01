"""Tenant-scoped management APIs for concrete integration connections."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.integrations.connections.service import disconnect_generic_connection
from app.integrations.core.registry import IntegrationRegistry
from app.models import IntegrationConnection, User
from app.schemas.integrations import (
    IntegrationConnectionEventOut,
    IntegrationConnectionListOut,
    IntegrationConnectionOut,
    IntegrationProviderOut,
)

router = APIRouter(prefix="/integrations", tags=["Integration management"])


@router.get("/providers", response_model=list[IntegrationProviderOut])
async def list_integration_providers(request: Request) -> list[IntegrationProviderOut]:
    """Return only providers with a registered, real adapter."""
    registry: IntegrationRegistry = request.app.state.integration_registry
    return [
        IntegrationProviderOut(
            provider_id=provider.provider_id,
            display_name=provider.display_name,
            version=provider.version,
            capabilities=sorted(capability.value for capability in provider.capabilities),
        )
        for provider in registry.list_providers()
    ]


@router.get("/connections", response_model=IntegrationConnectionListOut)
async def list_connections(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IntegrationConnectionListOut:
    if not 1 <= limit <= 100 or offset < 0:
        raise HTTPException(status_code=422, detail="Invalid pagination parameters")
    base = select(IntegrationConnection).where(
        IntegrationConnection.organization_id == user.organization_id
    )
    total = await db.scalar(select(func.count()).select_from(base.subquery()))
    rows = await db.scalars(
        base.order_by(IntegrationConnection.created_at.desc(), IntegrationConnection.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return IntegrationConnectionListOut(
        items=list(rows.all()),
        total=int(total or 0),
    )


@router.get("/connections/{connection_id}", response_model=IntegrationConnectionOut)
async def get_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> IntegrationConnectionOut:
    connection = await db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.organization_id == user.organization_id,
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    return IntegrationConnectionOut.model_validate(connection)


@router.post(
    "/connections/{connection_id}/disconnect",
    response_model=IntegrationConnectionEventOut,
)
async def disconnect_connection(
    connection_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_roles("owner", "admin")),
) -> IntegrationConnectionEventOut:
    connection = await db.scalar(
        select(IntegrationConnection)
        .where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.organization_id == user.organization_id,
        )
        .with_for_update()
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Integration connection not found")
    await disconnect_generic_connection(db, connection)
    return IntegrationConnectionEventOut(
        status="disconnected",
        message=f"{connection.display_name} was disconnected and its stored credentials were removed.",
    )
