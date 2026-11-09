"""Bounded, typed follow-up state attached to the delivered assistant message."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.features.ai.application.conversational_intents import classify_conversational_intent
from app.features.ai.application.order_reference import (
    order_reference_recovered,
    order_reference_unavailable,
)

PENDING_KEY = "support_pending_question"
PENDING_TTL = timedelta(minutes=30)
RefundReason = Literal["damaged", "defective", "incorrect", "change_of_mind"]
Stage = Literal[
    "refund_reason",
    "refund_item",
    "refund_verification",
    "refund_review",
    "order_confirmation",
    "order_verification",
    "product_selection",
    "policy_timing",
]
Intent = Literal["refund", "order", "shopping", "knowledge"]

REASON_PROMPT = "Was the item damaged, defective, incorrect, or did you change your mind?"
VERIFY_REFUND = "Thanks. Use the secure verification card to verify your order before the store team can review your refund request."
ORDER_REFERENCE_HELP = (
    "You can usually find the order number in your order confirmation email or order history. "
    "I can’t securely look up an order without that reference in this chat."
)
ORDER_HANDOFF_OFFER = " Would you like me to pass this conversation to the store’s support team?"
ORDER_HANDOFF_DECLINED = (
    "Okay. If you find the order number later, tell me and we can pick up here."
)
ORDER_HANDOFF_PENDING = "The store team has your request and can follow up here."
ORDER_HANDOFF_REQUESTED = (
    "I’ve passed this conversation to the store team. They can follow up here."
)
VERIFY_CODE_HELP = "Enter your code in the secure verification card. If it expired or didn’t arrive, use the card to request a fresh code."
_CODE_INTERRUPTED = re.compile(
    r"\b(?:code|otp)\b.{0,30}\b(?:expired|didn.t arrive|not working|invalid|missing)\b|"
    r"\b(?:lost|forgot|didn.t get|never got|no)\b.{0,25}\b(?:code|otp)\b",
    re.IGNORECASE,
)
YES = re.compile(
    r"(?:yes|yeah|yep|sure|ok(?:ay)?|please do|continue|yes please)[.! ]*", re.IGNORECASE
)
NO = re.compile(
    r"(?:no|no thanks|not now|never mind|nevermind|stop this request)[.! ]*", re.IGNORECASE
)
TOPIC_SWITCH = re.compile(
    r"\b(?:new question|unrelated|instead can|forget that|where is my|track my|"
    r"recommend|compare|shipping policy|return policy|refund policy|payment method|talk to|"
    r"delivery (?:costs?|charges?|fees?)|shipping (?:costs?|charges?|fees?)|"
    r"human|cancel (?:it|my order)|how (?:do|can)|what (?:is|are))\b",
    re.IGNORECASE,
)
REASON_PATTERNS: dict[RefundReason, str] = {
    "damaged": r"damaged|damage|broken|cracked",
    "defective": r"defective|faulty|doesn.t work|not working",
    "incorrect": r"incorrect|wrong(?: item| product| size| color| colour)?",
    "change_of_mind": r"change(?:d)? (?:of |my )?mind|no longer (?:want|need) it",
}
ITEM_IDENTIFIER = re.compile(r"^[\w][\w .,'’()&+/-]{1,119}$")
PRODUCT_ORDINAL = re.compile(
    r"(?:the )?(first|second|third|fourth|[1-4](?:st|nd|rd|th)?)(?: one| option)?[.!]?",
    re.IGNORECASE,
)
TIMING_ANSWER = re.compile(
    r"(?:today|tomorrow|this weekend|next week|on (?:mon|tues|wednes|thurs|fri|satur|sun)day)[.!]?",
    re.IGNORECASE,
)


class PendingQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active_intent: Intent
    stage: Stage
    expected_answer_type: Literal[
        "reason", "item", "otp", "confirmation", "ordinal", "time", "order_reference"
    ]
    refund_reason: RefundReason | None = None
    item_message_id: UUID | None = None
    verification_id: UUID | None = None
    verification_status: Literal["not_checked", "required", "verified"] = "not_checked"
    order_action: Literal["track", "cancel"] | None = None
    order_number_unavailable: bool = False
    order_reference_message_id: UUID | None = None
    handoff_status: Literal["offered", "declined", "requested"] | None = None
    ai_agent_id: UUID | None = None
    expires_at: datetime | None = None

    def attached_to(self, agent_id: UUID, now: datetime) -> dict[str, object]:
        return self.model_copy(
            update={
                "ai_agent_id": agent_id,
                "expires_at": now + PENDING_TTL,
            }
        ).model_dump(mode="json")


@dataclass(frozen=True)
class FollowUp:
    decision: str
    draft: str | None = None
    pending: PendingQuestion | None = None
    routed_question: str | None = None
    review: PendingQuestion | None = None
    handoff: bool = False


def refund_start() -> PendingQuestion:
    return PendingQuestion(
        active_intent="refund", stage="refund_reason", expected_answer_type="reason"
    )


def infer_assistant_question(text: str) -> PendingQuestion | None:
    """Recognize narrow legacy prompts. Inferred state can only ask or route."""
    from app.services import widget_ai

    folded = text[-800:].casefold()
    preview_handoff_states = {
        ORDER_REFERENCE_HELP + ORDER_HANDOFF_OFFER: "offered",
        ORDER_HANDOFF_DECLINED: "declined",
    }
    if text in preview_handoff_states:
        return order_verification_question().model_copy(
            update={
                "order_number_unavailable": True,
                "handoff_status": preview_handoff_states[text],
                "expected_answer_type": "confirmation"
                if text.endswith(ORDER_HANDOFF_OFFER)
                else "order_reference",
            }
        )
    if re.search(r"enter (?:the|your) order number and (?:your )?checkout email", folded):
        return order_verification_question()
    if text == widget_ai.ORDER_ACTION_REPLY:
        return order_verification_question(action="cancel")
    if (
        re.search(
            r"\b(?:reason for (?:your|the) (?:refund|return)|was (?:the|your) item damaged)\b",
            folded,
        )
        and "?" in folded
    ):
        return refund_start()
    if order := re.search(
        r"(?:would you like me to|should i) (check|track|cancel) (?:your|the) order\?", folded
    ):
        return PendingQuestion(
            active_intent="order",
            stage="order_confirmation",
            expected_answer_type="confirmation",
            order_action="cancel" if order[1] == "cancel" else "track",
        )
    if re.search(r"which (?:products?|options?|recommendations?|one)[^?]{0,85}\?", folded):
        return PendingQuestion(
            active_intent="shopping", stage="product_selection", expected_answer_type="ordinal"
        )
    if re.search(
        r"(?:when|what day|which day)[^?]{0,80}\b(?:deliver(?:ed|y)?|ship(?:ped)?|arrive)[^?]{0,30}\?",
        folded,
    ):
        return PendingQuestion(
            active_intent="knowledge", stage="policy_timing", expected_answer_type="time"
        )
    return None


def pending_from_assistant(
    turn: dict[str, str],
    agent_id: UUID,
    now: datetime,
    *,
    allow_legacy: bool = True,
) -> PendingQuestion | None:
    if turn.get("sender") != "assistant":
        return None
    try:
        if raw := turn.get(PENDING_KEY):
            state = PendingQuestion.model_validate_json(raw)
            if (
                state.ai_agent_id != agent_id
                or state.expires_at is None
                or state.expires_at.tzinfo is None
                or state.expires_at <= now
            ):
                return None
            return state
        if not allow_legacy:
            return None
        sent = datetime.fromisoformat(turn["created_at"])
        if sent.tzinfo is None or sent + PENDING_TTL <= now:
            return None
    except (ValueError, KeyError):
        return None
    return infer_assistant_question(turn.get("content", ""))


def _refund_reason(answer: str) -> RefundReason | None:
    answer = re.sub(
        r"^(?:actually[, ]+)?(?:(?:it|the item) (?:was|is) )?", "", answer, flags=re.IGNORECASE
    )
    for reason, pattern in REASON_PATTERNS.items():
        if re.fullmatch(pattern + r"[.! ]*", answer, re.IGNORECASE):
            return reason
    return None


def order_verification_question(*, action: Literal["track", "cancel"] = "track") -> PendingQuestion:
    return PendingQuestion(
        active_intent="order",
        stage="order_verification",
        expected_answer_type="order_reference",
        order_action=action,
        verification_status="required",
    )


def resolve_order_support(
    message: str,
    state: PendingQuestion | None = None,
    *,
    source_message_id: UUID | None = None,
) -> FollowUp | None:
    from app.services import widget_ai

    waiting_for_order = state is not None and state.stage in {
        "order_verification",
        "refund_verification",
    }
    in_order_context = waiting_for_order or (
        state is not None and state.stage == "order_confirmation"
    )
    if order_reference_unavailable(message, in_order_context=in_order_context):
        pending = (
            state
            if waiting_for_order and state
            else order_verification_question(
                action=(state.order_action if state else None) or "track"
            )
        )
        if pending.handoff_status == "requested":
            return FollowUp(
                "order_handoff_pending",
                draft=ORDER_HANDOFF_PENDING,
                pending=pending,
            )
        pending = pending.model_copy(
            update={
                "order_number_unavailable": True,
                "handoff_status": "offered",
                "expected_answer_type": "confirmation",
            }
        )
        return FollowUp(
            "order_reference_missing",
            draft=ORDER_REFERENCE_HELP + ORDER_HANDOFF_OFFER,
            pending=pending,
        )
    if not waiting_for_order or state is None:
        return None
    if order_reference_recovered(message):
        pending = state.model_copy(
            update={
                "order_number_unavailable": False,
                "handoff_status": None,
                "order_reference_message_id": source_message_id,
                "expected_answer_type": "otp"
                if state.stage == "refund_verification"
                else "order_reference",
            }
        )
        prompt = (
            VERIFY_REFUND
            if state.stage == "refund_verification"
            else widget_ai.ORDER_VERIFICATION_MESSAGE
        )
        if state.order_action == "cancel":
            prompt = widget_ai.ORDER_ACTION_REPLY
        return FollowUp("order_verification_resumed", draft=prompt, pending=pending)
    if state.active_intent == "order" and (social := classify_conversational_intent(message)):
        return FollowUp("order_context_retained", draft=social.widget_reply, pending=state)
    if not state.order_number_unavailable:
        if _CODE_INTERRUPTED.search(message) or (
            state.active_intent == "order" and re.fullmatch(r"\d{6}", message)
        ):
            return FollowUp("order_verification_interrupted", draft=VERIFY_CODE_HELP, pending=state)
        return None
    if widget_ai.HUMAN_REQUEST.search(message) or (
        state.handoff_status == "offered" and YES.fullmatch(message)
    ):
        if state.handoff_status == "requested":
            return FollowUp(
                "order_handoff_pending",
                draft=ORDER_HANDOFF_PENDING,
                pending=state,
            )
        pending = state.model_copy(
            update={"handoff_status": "requested", "expected_answer_type": "order_reference"}
        )
        return FollowUp(
            "order_handoff_requested",
            draft=ORDER_HANDOFF_REQUESTED,
            pending=pending,
            handoff=True,
        )
    if NO.fullmatch(message):
        if state.handoff_status == "requested":
            return FollowUp("order_handoff_pending", draft=ORDER_HANDOFF_PENDING, pending=state)
        pending = state.model_copy(
            update={"handoff_status": "declined", "expected_answer_type": "order_reference"}
        )
        return FollowUp(
            "order_handoff_declined",
            draft=ORDER_HANDOFF_DECLINED,
            pending=pending,
        )
    if (
        widget_ai.PURCHASE_INTENT.search(message)
        or (
            state.active_intent != "refund"
            and (widget_ai.REFUND_ACTION.search(message) or widget_ai.RETURN_ACTION.search(message))
        )
        or (
            TOPIC_SWITCH.search(message)
            and (
                not widget_ai.widget_request_needs_order_verification(message)
                or widget_ai.POLICY_QUESTION.search(message)
            )
        )
    ):
        return None
    if state.active_intent == "order" and widget_ai.CANCELLATION_REQUEST.search(message):
        state = state.model_copy(update={"order_action": "cancel"})
    if classify_conversational_intent(message) is None and (
        widget_ai.widget_request_needs_order_verification(message)
        or widget_ai.CLARIFICATION_REQUEST.fullmatch(message)
        or len(message.split()) <= 5
        and not TOPIC_SWITCH.search(message)
    ):
        if state.handoff_status == "requested":
            return FollowUp(
                "order_handoff_pending",
                draft=ORDER_HANDOFF_PENDING,
                pending=state,
            )
        return FollowUp(
            "order_reference_needed",
            draft=ORDER_REFERENCE_HELP + ORDER_HANDOFF_OFFER,
            pending=state.model_copy(
                update={"handoff_status": "offered", "expected_answer_type": "confirmation"}
            ),
        )
    return None


def resolve_follow_up(
    message: str,
    state: PendingQuestion,
    *,
    source_message_id: UUID | None,
) -> FollowUp | None:
    answer = " ".join(message.strip().split())
    if order_follow_up := resolve_order_support(answer, state, source_message_id=source_message_id):
        return order_follow_up
    if NO.fullmatch(answer) or (
        state.active_intent == "refund"
        and re.fullmatch(
            r"cancel (?:it|that|this request|my refund request)[.!]?", answer, re.IGNORECASE
        )
    ):
        return FollowUp(
            "declined", draft="Okay, I’ll leave that request there. What else can I help with?"
        )
    if state.stage == "order_confirmation" and (
        YES.fullmatch(answer)
        or re.fullmatch(r"cancel (?:it|that|this)[.!]?", answer, re.IGNORECASE)
    ):
        cancel = answer.lower().startswith("cancel") or state.order_action == "cancel"
        return FollowUp(
            "order_confirmation",
            routed_question=("Please cancel my order" if cancel else "Where is my order?"),
        )
    if TOPIC_SWITCH.search(answer):
        return None
    if state.active_intent == "refund":
        reason = _refund_reason(answer)
        if reason and state.stage != "refund_review":
            updated = state.model_copy(
                update={
                    "stage": "refund_item",
                    "expected_answer_type": "item",
                    "refund_reason": reason,
                }
            )
            label = {
                "damaged": "arrived damaged",
                "defective": "was defective",
                "incorrect": "was incorrect",
                "change_of_mind": "is no longer needed",
            }[reason]
            return FollowUp(
                "refund_reason",
                draft=f"Thanks for letting me know the item {label}. Which item was it? Share the product name and quantity, and leave out payment or contact details.",
                pending=updated,
            )
        if (
            state.stage == "refund_item"
            and state.refund_reason
            and source_message_id
            and (
                ITEM_IDENTIFIER.fullmatch(answer)
                and not re.search(r"\b\d{5,}\b", answer)
                and not YES.fullmatch(answer)
                and classify_conversational_intent(answer) is None
            )
        ):
            updated = state.model_copy(
                update={
                    "stage": "refund_verification",
                    "expected_answer_type": "otp",
                    "item_message_id": source_message_id,
                    "verification_status": "required",
                }
            )
            return FollowUp("refund_item", draft=VERIFY_REFUND, pending=updated)
        if state.stage == "refund_review" and YES.fullmatch(answer) and state.verification_id:
            return FollowUp("refund_review", review=state)
        if state.stage == "refund_verification" and YES.fullmatch(answer):
            return FollowUp("refund_verification", draft=VERIFY_REFUND, pending=state)
    if state.stage == "product_selection" and PRODUCT_ORDINAL.fullmatch(answer):
        return FollowUp("product_reference", routed_question=answer)
    if state.stage == "policy_timing" and TIMING_ANSWER.fullmatch(answer):
        return FollowUp(
            "policy_timing",
            routed_question=f"Store delivery policy for the requested time: {answer}",
        )
    return None


def assess_widget_follow_up(
    question: str,
    transcript: list[dict[str, str]],
    *,
    agent_id: UUID,
    source_message_id: UUID | None,
    now: datetime,
    allow_refund_workflow: bool = True,
) -> tuple[FollowUp | None, str]:
    from app.services import widget_ai

    previous = transcript
    if (
        previous
        and previous[-1].get("sender") == "customer"
        and (previous[-1].get("content", "") == question[:2000])
    ):
        previous = previous[:-1]
    if previous:
        state = pending_from_assistant(previous[-1], agent_id, now)
        if state is not None and (allow_refund_workflow or state.active_intent == "order"):
            if resolved := resolve_follow_up(question, state, source_message_id=source_message_id):
                return resolved, "resolved"
            if (
                not TOPIC_SWITCH.search(question)
                and classify_conversational_intent(question) is None
                and state.stage
                in {
                    "refund_reason",
                    "refund_item",
                    "refund_verification",
                    "refund_review",
                }
            ):
                prompts = {
                    "refund_reason": REASON_PROMPT,
                    "refund_item": "Which product and quantity are you asking to return?",
                    "refund_verification": VERIFY_REFUND,
                    "refund_review": "Would you like me to send the verified request to the store team for review?",
                }
                # An ambiguous short answer stays in the workflow, but is not treated as a valid slot.
                if len(question.split()) <= 5:
                    return FollowUp(
                        "targeted_clarification", draft=prompts[state.stage], pending=state
                    ), "ambiguous"
    if order_follow_up := resolve_order_support(" ".join(question.strip().split())):
        return order_follow_up, "started"
    if (
        allow_refund_workflow
        and widget_ai.REFUND_ACTION.search(question)
        and not (
            widget_ai.CANCELLATION_REQUEST.search(question)
            or widget_ai.HUMAN_REQUEST.search(question)
            or re.search(
                r"\b(?:refund policy|refund window|refund rules)\b", question, re.IGNORECASE
            )
        )
    ):
        return FollowUp("refund_start", draft=REASON_PROMPT, pending=refund_start()), "started"
    return None, "no_matching_pending_question"
