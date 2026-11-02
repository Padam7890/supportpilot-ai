"""Verified, conversation-scoped Shopify order context for widget replies."""

import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal, set_tenant_context
from app.models import WidgetOrderVerification
from app.services.widget_ai import format_verified_order_status

logger = logging.getLogger(__name__)
NON_ORDER_NUMBER_WORDS = frozenset(
    {"status", "update", "details", "detail", "tracking", "information", "number"}
)


def _question_order_number(question: str) -> str | None:
    match = re.search(r"#\s*([A-Za-z0-9][A-Za-z0-9-]{1,59})", question)
    if match is None:
        match = re.search(
            r"\border(?:\s+(?:number|no\.?))?\s+([A-Za-z0-9][A-Za-z0-9-]{2,59})\b",
            question,
            re.IGNORECASE,
        )
    if match is None:
        return None
    value = match.group(1).strip().lstrip("#")
    return None if value.casefold() in NON_ORDER_NUMBER_WORDS else value


async def verified_widget_order_reply(
    organization_id: UUID,
    conversation_id: UUID,
    question: str,
) -> tuple[bool, str | None]:
    """Reuse an unexpired OTP verification for the same conversation and order."""
    requested_number = _question_order_number(question)
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        verification = await db.scalar(
            select(WidgetOrderVerification)
            .where(
                WidgetOrderVerification.organization_id == organization_id,
                WidgetOrderVerification.conversation_id == conversation_id,
                WidgetOrderVerification.status == "verified",
                WidgetOrderVerification.expires_at > datetime.now(UTC),
            )
            .order_by(WidgetOrderVerification.verified_at.desc())
            .limit(1)
        )
        if verification is None:
            return False, None
        if (
            requested_number
            and requested_number.casefold() != verification.order_number.lstrip("#").casefold()
        ):
            return False, None
        email_encrypted = verification.customer_email_encrypted
        order_number = verification.order_number
        order_id = verification.shopify_order_id

    try:
        from app.integrations.providers.shopify.orders import lookup_authorized_order
        from app.integrations.providers.shopify.security import decrypt_credential
        from app.services.shopify_access import installation_for
        from app.services.shopify_order_lookup import map_order
        from app.services.shopify_tokens import valid_access_token

        email = decrypt_credential(email_encrypted)
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            installation = await installation_for(db, organization_id)
            access_token = await valid_access_token(db, installation)
            shop_domain = installation.shop_domain
        order = await lookup_authorized_order(
            shop_domain=shop_domain,
            access_token=access_token,
            order_number=order_number,
            customer_email=email,
        )
        if order is None or order.get("id") != order_id:
            return False, None
        mapped = map_order(order)
        return True, format_verified_order_status(mapped, opening="I checked your verified order")
    except Exception as exc:  # noqa: BLE001 - fail closed while retaining the verified session.
        logger.warning(
            "Verified widget order lookup failed: organization_id=%s conversation_id=%s error_type=%s",
            organization_id,
            conversation_id,
            type(exc).__name__,
        )
        return (
            True,
            "I’ve verified your order, but I’m having trouble checking its latest status right now. A support teammate can help.",
        )
