"""Small policy helpers for queued, tenant-scoped storefront AI replies."""

import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import AIExecution, Conversation, Message, SupportWidget

HANDOFF_MESSAGE = "I’ll pass this to a support teammate so they can help you."
AI_TEMPORARY_FAILURE_REPLY = (
    "I’m having trouble checking that right now. Please add any details that might help, and a support teammate can follow up here."
)
ORDER_VERIFICATION_MESSAGE = (
    "I can check that securely. A verification card is below; enter the order number and checkout email, "
    "and we’ll email a one-time code before sharing tracking details."
)
GREETING_REPLY = (
    "Hi there! I’m your store’s support assistant. I can help with order updates, product questions, "
    "and store policies. What can I help you with?"
)
THANKS_REPLY = "You’re welcome! Is there anything else I can help you with today?"
CAPABILITIES_REPLY = (
    "I can help find answers about this store, guide you through a secure order lookup, or pass a request "
    "to the support team. What would you like help with?"
)
ORDER_ACTION_REPLY = (
    "I can help submit a cancellation request. First, verify the order using the secure card below. "
    "The order will not be cancelled unless the store admin approves the request. Contact the store admin "
    "if you need help or an update."
)
VERIFIED_CANCELLATION_REPLY = (
    "Your order is verified. Use the cancellation request card below to submit your request. The order will not be "
    "cancelled unless the store admin approves it. Contact the store admin if you need help or an update."
)
REFUND_ACTION_REPLY = (
    "I’m sorry this hasn’t gone as expected. Returns, exchanges, and refunds need a store teammate’s review, "
    "and I won’t guess what an order qualifies for. Tell me what happened and I’ll pass the details to the team."
)
ACCOUNT_HELP_REPLY = (
    "For privacy, billing, account, and address changes need help from a support teammate. Please don’t share passwords "
    "or full payment details in chat; tell me what you need without including sensitive information."
)
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
SIMPLE_THANKS = re.compile(
    r"^(?:thanks|thank you|thx|cheers)(?: so much| a lot| there)?[!. ,]*$",
    re.IGNORECASE,
)
CAPABILITIES_QUESTION = re.compile(
    r"\b(?:what can you do|how can you help|can you help me|are you (?:a bot|an ai)|what are you)\b",
    re.IGNORECASE,
)
CLARIFICATION_REQUEST = re.compile(
    r"^(?:pardon(?: me)?|what do you mean|i(?:'m| am) confused|i don.t understand|huh|which card)[?.! ]*$",
    re.IGNORECASE,
)
CANCELLATION_REQUEST = re.compile(
    r"\b(?:cancel|cancellation|stop)\b.*\b(?:order|it|this|that|purchase)\b|"
    r"\b(?:cancel|cancellation)\s+(?:my|the)\s+(?:order|purchase)\b",
    re.IGNORECASE,
)
REFUND_ACTION = re.compile(
    r"\b(?:want|need|request|claim|get)\b.{0,30}\brefund\b|"
    r"\brefund\s+(?:me|my|this|the)\b|\bcharged twice\b",
    re.IGNORECASE,
)
RETURN_ACTION = re.compile(
    r"\b(?:send|ship)\b.{0,24}\bback\b|"
    r"\b(?:return|exchange)\b.{0,40}\b(?:item|product|order|it|this|that|purchase)\b|"
    r"\b(?:want|need)\b.{0,24}\b(?:return|exchange)\b",
    re.IGNORECASE,
)
HUMAN_REQUEST = re.compile(
    r"\b(?:human|person|agent|teammate|support representative|real person)\b",
    re.IGNORECASE,
)
PRIVATE_ACCOUNT_REQUEST = re.compile(
    r"\b(?:payment|charged|billing|address|account|personal data|private information|password)\b",
    re.IGNORECASE,
)
PRODUCT_QUESTION = re.compile(
    r"\b(?:product|item|size|colour|color|material|fabric|ingredient|in stock|available|price)\b",
    re.IGNORECASE,
)
POLICY_QUESTION = re.compile(
    r"\b(?:shipping|delivery|returns?|refunds?|exchange|policy|warranty|discount)\b",
    re.IGNORECASE,
)
PURCHASE_INTENT = re.compile(
    r"\b(?:"
    r"i\s+(?:want|need)\s+to\s+(?:buy|purchase|order)|"
    r"i(?:'d|\s+would)\s+like\s+to\s+(?:buy|purchase|order)|"
    r"can\s+i\s+(?:buy|purchase|order)|"
    r"how\s+(?:can|do)\s+i\s+(?:buy|purchase|order)|"
    r"how\s+to\s+(?:buy|purchase|order)|"
    r"(?:place|make)\s+(?:an?\s+)?order|"
    r"(?:buy|purchase|order)\s+(?:the\s+)?(?:first|second|third|fourth|one|this|that|it|product|item)|"
    r"add\s+(?:this|that|it|the\s+product|the\s+item)\s+to\s+(?:my\s+)?cart|"
    r"checkout\s+now"
    r")\b",
    re.IGNORECASE,
)
PURCHASE_HELP_REPLY = (
    "I can’t place orders or take payment in this chat. To buy the item, open its product page on the store and "
    "complete checkout there. If you tell me which product you mean, I can help you find it."
)


def widget_request_needs_human(message: str) -> bool:
    """Do not let unverified widget claims trigger private Shopify/account data."""
    return bool(SENSITIVE_REQUEST.search(message))


def widget_request_needs_order_verification(message: str) -> bool:
    return bool(re.search(r"\b(order|tracking|track|shipment|shipped|package|parcel)\b", message, re.IGNORECASE))


def widget_is_cancellation_request(message: str) -> bool:
    return bool(CANCELLATION_REQUEST.search(message))


def widget_purchase_reply(message: str) -> str | None:
    """Direct purchase requests to the merchant's own product page and checkout."""
    return PURCHASE_HELP_REPLY if PURCHASE_INTENT.search(message.strip()) else None


def widget_greeting_reply(message: str) -> str | None:
    """Return a deterministic greeting for a standalone greeting only."""
    normalized = message.strip()
    if SIMPLE_GREETING.fullmatch(normalized):
        return GREETING_REPLY
    if SIMPLE_THANKS.fullmatch(normalized):
        return THANKS_REPLY
    if CAPABILITIES_QUESTION.search(normalized):
        return CAPABILITIES_REPLY
    return None


def widget_clarification_reply(message: str, transcript: list[dict[str, str]]) -> str | None:
    """Explain a recent secure order step when a shopper asks for clarification."""
    if not CLARIFICATION_REQUEST.fullmatch(message.strip()):
        return None
    previous_assistant = next(
        (item.get("content", "") for item in reversed(transcript[:-1]) if item.get("sender") == "assistant"),
        "",
    )
    if re.search(r"\b(order|verification|one-time code|cancellation|cancel)\b", previous_assistant, re.IGNORECASE):
        return (
            "Sorry for the confusion. Use the secure order card in this chat: enter the order number and checkout email, "
            "then enter the one-time code sent to that email. After verification, you can submit a cancellation request; "
            "the store team must approve it before anything changes."
        )
    return "Sorry I wasn’t clear. Which part would you like me to explain? I can also bring in a support teammate."


def format_verified_order_status(order: Any, *, opening: str) -> str:
    """Describe Shopify order state without confusing fulfillment with cancellation."""
    parts = [f"{opening} {order.order_number}."]
    if order.cancelled_at:
        parts.append("Shopify shows this order was cancelled.")
        financial_status = (order.financial_status or "").replace("_", " ").lower()
        if financial_status:
            parts.append(f"Shopify payment status: {financial_status}.")
            if financial_status not in {"refunded", "partially refunded"}:
                parts.append("This does not confirm a refund; contact the store admin to check refund status.")
        return " ".join(parts)

    fulfillment = (order.fulfillment_status or "").strip()
    fulfillment_normalized = fulfillment.upper().replace(" ", "_")
    if fulfillment_normalized == "NOT_REQUIRED":
        parts.append("This order does not require fulfillment, so shipment tracking is not available.")
        return " ".join(parts)
    if fulfillment:
        parts.append(f"Fulfillment status: {fulfillment.replace('_', ' ').lower()}.")
    else:
        parts.append("The store has not marked this order as fulfilled yet.")

    tracking = order.tracking or []
    if tracking:
        info = tracking[0]
        details = [value for value in (info.company, info.number) if value]
        if details:
            parts.append("Tracking details: " + " · ".join(details) + ".")
        if info.url:
            parts.append(f"Tracking link: {info.url}")
    else:
        parts.append("The store has not provided tracking information for this order yet.")
    return " ".join(parts)


def widget_sensitive_reply(message: str) -> tuple[str, str] | None:
    """Handle workflows that must not be answered from unverified customer claims."""
    normalized = message.strip()
    if CANCELLATION_REQUEST.search(normalized):
        return ORDER_ACTION_REPLY, "The shopper requested an order change that requires verification and human approval."
    if REFUND_ACTION.search(normalized) or RETURN_ACTION.search(normalized):
        return REFUND_ACTION_REPLY, "The shopper requested a return, exchange, or refund review. Eligibility was not inferred."
    if widget_request_needs_order_verification(normalized):
        return ORDER_VERIFICATION_MESSAGE, "The shopper must verify the order before private order details can be shared."
    if HUMAN_REQUEST.search(normalized):
        return HANDOFF_MESSAGE, "The shopper explicitly requested a support teammate."
    if PRIVATE_ACCOUNT_REQUEST.search(normalized):
        return ACCOUNT_HELP_REPLY, "The shopper asked about private account or billing information and needs a support teammate."
    return None


def widget_missing_knowledge_reply(message: str) -> str:
    """Offer a useful, specific next step without inventing store policy or product facts."""
    if PRODUCT_QUESTION.search(message):
        return (
            "I’d be happy to help with that product. Which item are you looking at? Share its name or product-page link, "
            "and I’ll check the store’s available information. I’ll ask a teammate to confirm anything that isn’t listed."
        )
    if POLICY_QUESTION.search(message):
        return (
            "I want to give you the store’s exact policy, not guess. I don’t have verified details for that question yet. "
            "Could you tell me which part you need help with? I can also ask a teammate to confirm it."
        )
    return (
        "I’m happy to help, but I don’t have enough verified store information to answer that accurately yet. "
        "Could you share a little more detail? I can also pass your question to a support teammate."
    )


async def enqueue_widget_reply(
    *,
    db: AsyncSession,
    widget: SupportWidget,
    conversation: Conversation,
    message: Message,
) -> AIExecution | None:
    if not widget.ai_enabled or conversation.ai_mode != "ai":
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
