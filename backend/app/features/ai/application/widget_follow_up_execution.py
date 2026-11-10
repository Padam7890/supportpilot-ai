"""Widget follow-up completion with explicit verification and retrieval stages.

A verified refund request is only escalated for staff review. No refund
mutation is authorized or performed by this service.
"""

from dataclasses import dataclass
from uuid import UUID

from app.features.ai.application.context import load_execution_context
from app.features.ai.application.follow_up import FollowUp, VERIFY_REFUND
from app.features.ai.application.widget_orders import refund_verification_is_active
from app.features.ai.application.widget_replies import finish_widget_reply


class FollowUpRetrievalUnavailable(RuntimeError):
    """Verified follow-up retrieval did not return a running execution."""


@dataclass(frozen=True)
class FollowUpCompletion:
    completed: bool
    failure_stage: str | None = None


async def complete_widget_follow_up(
    organization_id: UUID,
    execution_id: UUID,
    conversation_id: UUID,
    *,
    follow_up: FollowUp,
    delivery_status: str,
) -> FollowUpCompletion:
    """Complete a deterministic follow-up, or defer to normal routing."""
    if not (follow_up.draft or follow_up.review):
        return FollowUpCompletion(completed=False)
    draft, next_question, reply_status = (
        follow_up.draft, follow_up.pending, delivery_status
    )
    review_citations = []
    safe_summary = "The shopper continued a support workflow."
    if follow_up.handoff:
        reply_status = "escalated"
        safe_summary = (
            "The shopper requested support because their order reference was unavailable."
        )
    if review := follow_up.review:
        if (
            review.verification_id and review.item_message_id and review.refund_reason
            and await refund_verification_is_active(
                organization_id, conversation_id, review.verification_id
            )
        ):
            policy = await load_execution_context(
                organization_id, execution_id, include_knowledge=True,
                follow_up_query=(
                    "refund return eligibility policy "
                    f"{review.refund_reason.replace('_', ' ')}"
                ),
            )
            if policy is None:
                raise FollowUpRetrievalUnavailable("verified follow-up retrieval unavailable")
            review_citations = policy[4]
            draft = (
                "I’ll send your verified refund request to the store team to check "
                "eligibility. No refund has been issued."
            )
            reply_status = "escalated"
            safe_summary = (
                "The shopper verified their order and requested staff review for refund eligibility."
            )
            failure_stage = "knowledge_retrieval"
        else:
            draft = VERIFY_REFUND
            next_question = review.model_copy(update={
                "stage": "refund_verification",
                "expected_answer_type": "otp",
                "verification_status": "required",
                "verification_id": None,
            })
            failure_stage = "refund_verification"
    else:
        failure_stage = None
    await finish_widget_reply(
        organization_id, execution_id, draft=draft or "",
        reply_status=reply_status, safe_summary=safe_summary,
        citations=review_citations,
        outcomes=[{
            "tool": "widget_follow_up", "status": follow_up.decision,
            "result_count": len(review_citations),
        }],
        usage={}, model_name=None, pending_question=next_question,
    )
    return FollowUpCompletion(completed=True, failure_stage=failure_stage)
