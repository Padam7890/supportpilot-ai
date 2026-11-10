"""Authorized widget order support responses.

This application service does not perform cancellations or refunds.
All order facts are obtained through the existing verified order lookup.
"""

from uuid import UUID

from app.features.ai.application.conversation_orchestration import CustomerTurnPlan
from app.features.ai.application.follow_up import order_verification_question
from app.features.ai.application.widget_orders import verified_widget_order_reply
from app.features.ai.application.widget_replies import finish_widget_reply
from app.services.widget_ai import (
    ORDER_VERIFICATION_MESSAGE,
    VERIFIED_CANCELLATION_REPLY,
    widget_is_cancellation_request,
    widget_request_needs_order_verification,
)


async def complete_sensitive_widget_turn(
    organization_id: UUID,
    execution_id: UUID,
    conversation_id: UUID,
    *,
    question: str,
    turn: CustomerTurnPlan,
    delivery_status: str,
    outcomes: list[dict],
) -> None:
    """Resolve a sensitive route without granting commerce-action permission."""
    if turn.route != "sensitive":
        raise ValueError("Sensitive widget handler requires a sensitive route")

    draft = turn.draft or ""
    reply_status = turn.reply_status
    safe_summary = turn.safe_summary or ""
    pending_order = None
    if widget_is_cancellation_request(question):
        order_verified, _order_reply = await verified_widget_order_reply(
            organization_id, conversation_id, question
        )
        if order_verified:
            draft = VERIFIED_CANCELLATION_REPLY
            safe_summary = (
                "A previously verified order cancellation still requires human approval."
            )
        else:
            pending_order = order_verification_question(action="cancel")
    elif widget_request_needs_order_verification(question):
        order_verified, order_reply = await verified_widget_order_reply(
            organization_id, conversation_id, question
        )
        if order_verified:
            draft = order_reply or (
                "Your order is verified, but I couldn’t retrieve its latest status. "
                "A store teammate can follow up here."
            )
            reply_status = (
                "escalated"
                if order_reply is None or "teammate can help" in order_reply.casefold()
                else delivery_status
            )
            safe_summary = (
                "A current Shopify order lookup used the shopper’s active email verification."
            )
        elif draft == ORDER_VERIFICATION_MESSAGE:
            pending_order = order_verification_question()
    await finish_widget_reply(
        organization_id,
        execution_id,
        draft=draft,
        reply_status=reply_status,
        safe_summary=safe_summary,
        citations=[],
        outcomes=outcomes,
        usage={},
        model_name=None,
        pending_question=pending_order,
    )
