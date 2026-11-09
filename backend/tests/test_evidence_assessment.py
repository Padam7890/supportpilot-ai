"""Evidence assessment foundation tests."""
from app.features.ai.application.evidence_assessment import assess_knowledge_evidence


def test_no_sources_never_claim_support() -> None:
    result = assess_knowledge_evidence("What is your refund policy?", [])
    assert not result.supported
    assert result.reason == "no_sources"


def test_unrelated_excerpt_does_not_claim_support() -> None:
    result = assess_knowledge_evidence(
        "What is your refund policy?", ["Our warehouse is open Monday through Friday."]
    )
    assert not result.supported


def test_lexical_match_is_only_a_candidate() -> None:
    result = assess_knowledge_evidence(
        "What is your refund policy?", ["Refund requests are reviewed by the store team."]
    )
    assert result.supported
    assert result.reason == "lexical_candidate_only"


def test_ambiguous_question_not_supported() -> None:
    result = assess_knowledge_evidence("What is it?", ["Refund policy details"])
    assert not result.supported
