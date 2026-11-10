"""Verified, conversation-scoped Shopify order context for widget replies."""

import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal, set_tenant_context
from app.features.ai.application.order_action_policy import authorize_order_action
from app.integrations.core.contracts.provider import IntegrationConnectionRef
from app.integrations.core.interfaces import CommerceCapability
from app.integrations.core.types import IntegrationCapability
from app.integrations.registry import build_integration_registry
from app.models import IntegrationConnection, WidgetOrderVerification
from app.schemas.shopify import ShopifyOrderOut
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
        policy = authorize_order_action(
            "track",
            verified=verification is not None,
            verification_tenant_matches=(
                verification is not None and verification.organization_id == organization_id
            ),
            verification_conversation_matches=(
                verification is not None and verification.conversation_id == conversation_id
            ),
        )
        if policy.decision != "allow_read":
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
        from app.integrations.providers.shopify.security import decrypt_credential

        email = decrypt_credential(email_encrypted)
        async with SessionLocal() as db:
            await set_tenant_context(db, organization_id)
            connection = await db.scalar(
                select(IntegrationConnection).where(
                    IntegrationConnection.organization_id == organization_id,
                    IntegrationConnection.provider_id == "shopify",
                    IntegrationConnection.status == "connected",
                )
            )
            if connection is None:
                return True, (
                    "I’ve verified your order, but the store connection is unavailable right now. "
                    "A support teammate can help."
                )
            connection_ref = IntegrationConnectionRef(
                id=connection.id,
                organization_id=connection.organization_id,
                provider_id=connection.provider_id,
                external_account_id=connection.external_account_id,
            )

        commerce = build_integration_registry().get_capability(
            "shopify", IntegrationCapability.COMMERCE, CommerceCapability
        )
        order = await commerce.lookup_order(
            connection_ref,
            order_number=order_number,
            verified_customer_email=email,
        )
        if order is None or order.get("id") != order_id:
            return False, None
        mapped = ShopifyOrderOut.model_validate(order)
        # A lexical citation/number check cannot establish semantic correctness
        # of order status, tracking, cancellation or refund claims. Deliver only
        # the deterministic formatter backed by this authorized Shopify lookup.
        # Keep natural-language composition for non-sensitive support turns.
        return True, format_verified_order_status(
            mapped, opening="I checked your verified order",
        )
    except Exception as exc:  # noqa: BLE001 - verified fallback, no private payloads in logs.
            logger.warning(
                "Verified order composition unavailable: organization_id=%s error_type=%s",
                organization_id, type(exc).__name__,
            )
        return True, fallback
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


async def refund_verification_is_active(
    organization_id: UUID, conversation_id: UUID, verification_id: UUID
) -> bool:
    """Recheck the specific OTP grant that belongs to this refund continuation."""
    async with SessionLocal() as db:
        await set_tenant_context(db, organization_id)
        verification = await db.scalar(
            select(WidgetOrderVerification).where(
                WidgetOrderVerification.id == verification_id,
                WidgetOrderVerification.organization_id == organization_id,
                WidgetOrderVerification.conversation_id == conversation_id,
                WidgetOrderVerification.status == "verified",
                WidgetOrderVerification.expires_at > datetime.now(UTC),
            )
        )
        decision = authorize_order_action(
            "refund",
            verified=verification is not None,
            verification_tenant_matches=(
                verification is not None and verification.organization_id == organization_id
            ),
            verification_conversation_matches=(
                verification is not None and verification.conversation_id == conversation_id
            ),
        )
        return decision.decision == "request_human_review"
