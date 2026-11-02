"""Bounded cleanup for expired shopper order-verification secrets."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select

from app.db.session import SessionLocal, set_tenant_context
from app.models import WidgetOrderVerification

VERIFICATION_RETENTION = timedelta(hours=24)
VERIFICATION_PURGE_BATCH = 100


async def purge_expired_order_verifications(organization_id: UUID) -> int:
    """Delete a bounded batch after short-lived OTP data is no longer useful."""
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        expired_ids = (
            select(WidgetOrderVerification.id)
            .where(
                WidgetOrderVerification.organization_id == organization_id,
                WidgetOrderVerification.expires_at < datetime.now(UTC) - VERIFICATION_RETENTION,
            )
            .order_by(WidgetOrderVerification.expires_at, WidgetOrderVerification.id)
        )
        expired_ids = expired_ids.with_for_update(skip_locked=True).limit(VERIFICATION_PURGE_BATCH)
        result = await db.execute(
            delete(WidgetOrderVerification).where(
                WidgetOrderVerification.organization_id == organization_id,
                WidgetOrderVerification.id.in_(expired_ids),
            )
        )
        deleted_count = result.rowcount or 0
        await db.commit()
        return deleted_count
