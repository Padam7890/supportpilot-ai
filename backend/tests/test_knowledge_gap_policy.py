from app.features.ai.domain.knowledge_gap_policy import detect_knowledge_gap, faq_suggestion

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
