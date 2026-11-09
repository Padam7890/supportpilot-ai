"""Bounded, typed follow-up state attached to the delivered assistant message."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.features.ai.application.conversational_intents import classify_conversational_intent

PENDING_KEY = "support_pending_question"
PENDING_TTL = timedelta(minutes=30)
RefundReason = Literal["damaged", "defective", "incorrect", "change_of_mind"]
Stage = Literal[
    "refund_reason",
    "refund_item",
    "refund_verification",
    "refund_review",
    "order_confirmation",
    "product_selection",
    "policy_timing",
]
Intent = Literal["refund", "order", "shopping", "knowledge"]

REASON_PROMPT = "Was the item damaged, defective, incorrect, or did you change your mind?"
VERIFY_REFUND = "Thanks. Use the secure verification card to verify your order before the store team can review your refund request."
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
    expected_answer_type: Literal["reason", "item", "otp", "confirmation", "ordinal", "time"]
    refund_reason: RefundReason | None = None
    item_message_id: UUID | None = None
    verification_id: UUID | None = None
    verification_status: Literal["not_checked", "required", "verified"] = "not_checked"
    order_action: Literal["track", "cancel"] | None = None
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


def refund_start() -> PendingQuestion:
    return PendingQuestion(
        active_intent="refund", stage="refund_reason", expected_answer_type="reason"
    )


def infer_assistant_question(text: str) -> PendingQuestion | None:
    """Recognize narrow legacy prompts. Inferred state can only ask or route."""
    folded = text[-800:].casefold()
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


def resolve_follow_up(
    message: str,
    state: PendingQuestion,
    *,
    source_message_id: UUID | None,
) -> FollowUp | None:
    answer = " ".join(message.strip().split())
    if NO.fullmatch(answer) or (
        state.active_intent == "refund"
        and re.fullmatch(
            r"cancel (?:it|that|this request|my refund request)[.!]?", answer, re.IGNORECASE
        )
    ):
        return FollowUp(
            "declined", draft="Okay, I’ll leave that request there. What else can I help with?"
        )
    if state.active_intent == "order" and (
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
        if state is not None:
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
    if widget_ai.REFUND_ACTION.search(question) and not (
        widget_ai.CANCELLATION_REQUEST.search(question)
        or widget_ai.HUMAN_REQUEST.search(question)
        or re.search(r"\b(?:refund policy|refund window|refund rules)\b", question, re.IGNORECASE)
    ):
        return FollowUp("refund_start", draft=REASON_PROMPT, pending=refund_start()), "started"
    return None, "no_matching_pending_question"
