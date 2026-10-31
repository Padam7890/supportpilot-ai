"""Small policy helpers for queued, tenant-scoped storefront AI replies."""

import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AIExecution, Conversation, Message, SupportWidget

HANDOFF_MESSAGE = "I’ll pass this to a support teammate so they can help you."
GREETING_REPLY = "Hi! How can I help you today?"
SENSITIVE_REQUEST = re.compile(
    r"\b(order|tracking|track my|shipment|shipped|package|parcel|cancel|cancellation|"
    r"refund|return|exchange|payment|charged|billing|address|change my|account|"
    r"personal data|private information|password)\b",
    re.IGNORECASE,
)
SIMPLE_GREETING = re.compile(
    r"^(?:hi|hello|hey|good morning|good afternoon|good evening)(?: there)?[!. ,]*$",
    re.IGNORECASE,
)


def widget_request_needs_human(message: str) -> bool:
    """Do not let unverified widget claims trigger private Shopify/account data."""
    return bool(SENSITIVE_REQUEST.search(message))


def widget_greeting_reply(message: str) -> str | None:
    """Return a deterministic greeting for a standalone greeting only."""
    return GREETING_REPLY if SIMPLE_GREETING.fullmatch(message.strip()) else None


async def enqueue_widget_reply(
    *,
    db: AsyncSession,
    widget: SupportWidget,
    conversation: Conversation,
    message: Message,
) -> AIExecution | None:
    if not widget.ai_enabled:
        return None
    execution = AIExecution(
        organization_id=widget.organization_id,
        requested_by_user_id=None,
        conversation_id=conversation.id,
        source_message_id=message.id,
        kind="widget_reply",
        status="queued",
        delivery_mode=widget.ai_reply_mode,
        reply_status="processing",
        question=message.content,
        max_attempts=settings.ai_provider_max_attempts,
    )
    db.add(execution)
    await db.flush()
    return execution
