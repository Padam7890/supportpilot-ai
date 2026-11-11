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
    elif retrieval_outcome == "retrieved" and answer_grounded is False:
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
