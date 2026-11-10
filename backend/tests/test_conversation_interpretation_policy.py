"""Policy regression scenarios for opt-in model-first interpretation."""

from app.features.ai.application.conversation_interpretation_policy import (
    ConversationInterpretationPolicy,
)


def test_legacy_behavior_remains_default() -> None:
    policy = ConversationInterpretationPolicy(model_first=False)
    assert not policy.should_use_model(
        risk_level="low", negated_action=False,
        needs_clarification=False, legacy_router_would_invoke=False,
    )


def test_model_first_interprets_non_sensitive_questions() -> None:
    policy = ConversationInterpretationPolicy(model_first=True)
    assert policy.should_use_model(
        risk_level="low", negated_action=False,
        needs_clarification=False, legacy_router_would_invoke=False,
    )


def test_high_risk_action_does_not_get_model_first_upgrade() -> None:
    policy = ConversationInterpretationPolicy(model_first=True)
    assert not policy.should_use_model(
        risk_level="high", negated_action=False,
        needs_clarification=False, legacy_router_would_invoke=False,
    )


def test_negation_and_missing_context_use_safe_path() -> None:
    policy = ConversationInterpretationPolicy(model_first=True)
    for negated, unclear in ((True, False), (False, True)):
        assert not policy.should_use_model(
            risk_level="low", negated_action=negated,
            needs_clarification=unclear, legacy_router_would_invoke=True,
        )
