from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.db.session import get_db
from app.models import CatalogProduct, RecommendationSettings, User
from app.schemas.recommendation_settings import RecommendationSettingsIn, RecommendationSettingsOut

router = APIRouter(prefix="/recommendation-settings", tags=["recommendation settings"])


def settings_out(row: RecommendationSettings) -> RecommendationSettingsOut:
    return RecommendationSettingsOut.model_validate(row)


@router.get("", response_model=RecommendationSettingsOut)
async def get_settings(db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("owner", "admin", "agent", "viewer"))) -> RecommendationSettingsOut:
    row = await db.scalar(select(RecommendationSettings).where(RecommendationSettings.organization_id == user.organization_id))
    if row is None:
        row = RecommendationSettings(organization_id=user.organization_id)
        db.add(row)
        await db.flush()
    return settings_out(row)


@router.put("", response_model=RecommendationSettingsOut)
async def update_settings(payload: RecommendationSettingsIn, db: AsyncSession = Depends(get_db), user: User = Depends(require_roles("owner", "admin"))) -> RecommendationSettingsOut:
    product_ids = payload.excluded_product_ids
    if product_ids:
        found = set(await db.scalars(select(CatalogProduct.id).where(
            CatalogProduct.organization_id == user.organization_id,
            CatalogProduct.id.in_(product_ids),
        )))
        if found != set(product_ids):
            raise HTTPException(status_code=422, detail="Excluded products must belong to this organization")
    row = await db.scalar(select(RecommendationSettings).where(RecommendationSettings.organization_id == user.organization_id).with_for_update())
    values = payload.model_dump(mode="json")
    if row is None:
        row = RecommendationSettings(organization_id=user.organization_id, **values)
        db.add(row)
    else:
        for key, value in values.items():
            setattr(row, key, value)
    await db.flush()
    return settings_out(row)
