"""Conservative, provider-independent classification of missing knowledge.

This policy consumes *structured* retrieval/generation outcomes, not customer
phrasing. It must never infer a knowledge gap solely from an empty citation
list: greetings, order tools and safe refusals often have no citations.
"""
from dataclasses import dataclass
from enum import StrEnum


class GapReason(StrEnum):
    NO_RELEVANT_EVIDENCE = "no_relevant_evidence"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class KnowledgeGapSignal:
    organization_id: str
    conversation_id: str
    source_message_id: str
    question: str
    reason: GapReason


def detect_knowledge_gap(
    *,
    organization_id: str,
    conversation_id: str,
    source_message_id: str,
    question: str,
    intent: str,
    retrieval_outcome: str,
    answer_grounded: bool | None,
) -> KnowledgeGapSignal | None:
    """Return a candidate only for a confirmed unanswered knowledge request.

    Callers must supply validated tenant-owned identifiers and a structured
    retrieval outcome. A model's free-form reply must not be parsed to guess.
    """
    if intent != "knowledge" or not question.strip():
        return None
    if retrieval_outcome == "no_relevant_evidence":
        reason = GapReason.NO_RELEVANT_EVIDENCE
    elif retrieval_outcome == "insufficient_evidence" or (\n        retrieval_outcome == "retrieved" and answer_grounded is False\n    ):
        reason = GapReason.INSUFFICIENT_EVIDENCE
    else:
        return None
    return KnowledgeGapSignal(
        organization_id=organization_id,
        conversation_id=conversation_id,
        source_message_id=source_message_id,
        question=question.strip()[:1000],
        reason=reason,
    )


def faq_suggestion(question: str, approved_evidence: str | None = None) -> dict[str, str | None]:
    """Prepare a review-only FAQ; never manufacture a policy or answer."""
    return {
        "question": question.strip()[:1000],
        "suggested_answer": approved_evidence.strip() if approved_evidence and approved_evidence.strip() else None,
        "status": "needs_review",
    }


def eligible_widget_knowledge_gap(
    *,
    route: str | None,
    requires_evidence: bool,
    policy_follow_up_kind: str | None = None,
    has_commerce_follow_up: bool = False,
    should_clarify: bool = False,
    multi_intent: bool = False,
) -> bool:
    """Determine whether a widget turn is a store-knowledge question.

    Use the resolved structured route and evidence requirement, not keyword
    matching or the wording of the generated reply. Only policy-question
    follow-ups qualify; order/refund/date workflows are deliberately excluded.
    """
    if not requires_evidence or has_commerce_follow_up or should_clarify or multi_intent:
        return False
    if policy_follow_up_kind is not None:
        return policy_follow_up_kind == "policy_question"
    return route == "knowledge"
