"""Phase 8: deterministic regression matrix for conversation safety and routing.

These cases exercise pure routing decisions; they do not replace end-to-end
Shopify, RAG, browser streaming, or tenant-isolation integration tests.
"""
import pytest

from app.features.ai.application.conversation_orchestration import plan_widget_turn
from app.features.ai.application.evidence_assessment import assess_knowledge_evidence
from app.features.ai.application.order_action_policy import authorize_order_action


@pytest.mark.parametrize(
    "question",
    [
        "tell me a joke",
        "make me laugh",
        "what is the meaning of life",
        "can you write a poem",
        "solve homework",
    ],
)
def test_off_topic_does_not_enter_store_knowledge(question: str) -> None:
    result = plan_widget_turn(question, [])
    assert result.route == "direct"


@pytest.mark.parametrize(
    "question",
    [
        "what about that?",
        "and this one?",
    ],
)
def test_unanchored_followup_requires_clarification(question: str) -> None:
    result = plan_widget_turn(question, [])
    assert result.route == "clarification"


@pytest.mark.parametrize(
    "question",
    [
        "what is your refund policy?",
        "what about shipping?",
        "what payment methods do you accept?",
    ],
)
def test_explicit_support_topics_keep_knowledge_route(question: str) -> None:
    result = plan_widget_turn(question, [])
    assert result.route == "knowledge"


@pytest.mark.parametrize(
    "question,excerpts,reason",
    [
        ("refund policy", [], "no_sources"),
        ("refund policy", ["We open at nine."], "insufficient_lexical_overlap"),
        ("what is it?", ["Refund policy"], "query_too_ambiguous"),
        ("refund policy", ["Refund policy is available."], "lexical_candidate_only"),
    ],
)
def test_evidence_diagnostics(question: str, excerpts: list[str], reason: str) -> None:
    assert assess_knowledge_evidence(question, excerpts).reason == reason


@pytest.mark.parametrize("action", ["track", "cancel", "refund", "return"])
@pytest.mark.parametrize(
    "verified,tenant_ok,conversation_ok",
    [
        (False, True, True),
        (True, False, True),
        (True, True, False),
        (True, False, False),
    ],
)
def test_order_actions_fail_closed_without_matching_verification(
    action: str, verified: bool, tenant_ok: bool, conversation_ok: bool
) -> None:
    decision = authorize_order_action(
        action,
        verified=verified,
        verification_tenant_matches=tenant_ok,
        verification_conversation_matches=conversation_ok,
    )
    assert decision.decision == "request_verification"


@pytest.mark.parametrize("action", ["cancel", "refund", "return"])
def test_verified_mutations_still_need_review(action: str) -> None:
    decision = authorize_order_action(
        action,
        verified=True,
        verification_tenant_matches=True,
        verification_conversation_matches=True,
    )
    assert decision.decision == "request_human_review"
