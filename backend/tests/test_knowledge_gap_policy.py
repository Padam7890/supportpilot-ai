from app.features.ai.domain.knowledge_gap_policy import (
    detect_knowledge_gap, eligible_widget_knowledge_gap, faq_suggestion,\n)

BASE = {
    "organization_id": "tenant-a",
    "conversation_id": "conversation-a",
    "source_message_id": "message-a",
    "question": "Do you deliver to Pokhara?",
    "intent": "knowledge",
    "retrieval_outcome": "no_relevant_evidence",
    "answer_grounded": None,
}


def test_missing_knowledge_creates_candidate():
    gap = detect_knowledge_gap(**BASE)
    assert gap is not None
    assert gap.question == "Do you deliver to Pokhara?"
    assert gap.reason == "no_relevant_evidence"
    assert gap.organization_id == "tenant-a"


def test_grounded_retrieval_does_not_create_gap():
    assert detect_knowledge_gap(**{**BASE, "retrieval_outcome": "retrieved", "answer_grounded": True}) is None


def test_unsupported_evidence_creates_gap():
    assert detect_knowledge_gap(**{**BASE, "retrieval_outcome": "retrieved", "answer_grounded": False}) is not None


def test_order_request_is_not_a_knowledge_gap():
    assert detect_knowledge_gap(**{**BASE, "intent": "order"}) is None


def test_unknown_outcome_does_not_create_gap():
    assert detect_knowledge_gap(**{**BASE, "retrieval_outcome": "provider_failed"}) is None


def test_faq_never_invents_an_answer():
    assert faq_suggestion("Do you deliver to Pokhara?") == {
        "question": "Do you deliver to Pokhara?",
        "suggested_answer": None,
        "status": "needs_review",
    }


def test_faq_accepts_only_explicit_approved_evidence():
    assert faq_suggestion("Delivery?", "  Verified policy  ")["suggested_answer"] == "Verified policy"


def test_unanswered_delivery_question_is_eligible_and_detected():
    assert eligible_widget_knowledge_gap(route="knowledge", requires_evidence=True)
    signal = detect_knowledge_gap(**{
        **BASE,
        "question": "Do you deliver your order to Pokhara?",
        "retrieval_outcome": "no_relevant_evidence",
    })
    assert signal is not None
    assert signal.question == "Do you deliver your order to Pokhara?"


def test_unanswered_policy_follow_up_is_eligible():
    assert eligible_widget_knowledge_gap(
        route=None, requires_evidence=True, policy_follow_up_kind="policy_question",
    )


def test_private_order_and_commerce_flows_are_not_knowledge_gaps():
    for route in ("sensitive", "purchase", "inventory", "direct", "clarification"):
        assert not eligible_widget_knowledge_gap(route=route, requires_evidence=True)
    assert not eligible_widget_knowledge_gap(
        route="knowledge", requires_evidence=True, has_commerce_follow_up=True,
    )
    assert not eligible_widget_knowledge_gap(
        route=None, requires_evidence=True, policy_follow_up_kind="refund",
    )
    assert not eligible_widget_knowledge_gap(
        route=None, requires_evidence=True, policy_follow_up_kind="delivery_date",
    )


def test_ambiguous_or_multi_intent_questions_are_not_recorded():
    assert not eligible_widget_knowledge_gap(
        route="knowledge", requires_evidence=True, should_clarify=True,
    )
    assert not eligible_widget_knowledge_gap(
        route="knowledge", requires_evidence=True, multi_intent=True,
    )
    assert not eligible_widget_knowledge_gap(
        route="knowledge", requires_evidence=False,
    )


def test_insufficient_evidence_creates_gap_even_when_safe_reply_was_accepted():
    gap = detect_knowledge_gap(**{
        **BASE,
        "retrieval_outcome": "insufficient_evidence",
        "answer_grounded": True,
    })
    assert gap is not None
    assert gap.reason == "insufficient_evidence"


def test_answered_question_does_not_create_gap():
    assert detect_knowledge_gap(**{
        **BASE,
        "retrieval_outcome": "retrieved",
        "answer_grounded": True,
    }) is None
