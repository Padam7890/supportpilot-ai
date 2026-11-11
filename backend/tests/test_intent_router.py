import json

import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.features.ai.application.intent_routing.deterministic import assess_deterministic_route
from app.features.ai.application.intent_routing.llm_router import _parse_router_json
from app.features.ai.application.intent_routing.metrics import reset_aggregate_for_tests
from app.features.ai.application.intent_routing.policy import should_invoke_llm_router
from app.features.ai.application.intent_routing.schemas import (
    Intent,
    IntentDecision,
    RoutingDecision,
)
from app.features.ai.application.intent_routing.service import (
    apply_routing_to_widget_plan,
    resolve_customer_routing,
)


def test_high_confidence_greeting_skips_llm_router():
    assessment = assess_deterministic_route("Hello there!", [])
    assert assessment.confidence >= 0.9
    assert not should_invoke_llm_router(assessment, "Hello there!")


def test_multi_intent_competing_invokes_llm_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "ai_intent_router_enabled", True)
    assessment = assess_deterministic_route("My order is late and I want a refund.", [])
    assert assessment.competing
    assert should_invoke_llm_router(assessment, "My order is late and I want a refund.")


def test_invalid_router_json_rejected():
    with pytest.raises((json.JSONDecodeError, ValueError)):
        _parse_router_json("not json")
    with pytest.raises(ValidationError):
        RoutingDecision.model_validate(
            {
                "intents": [{"intent": "not_real", "confidence": 0.5, "requires_knowledge": True, "requires_tools": False}],
                "reason_code": "test",
            }
        )


def test_routing_decision_schema_accepts_valid_payload():
    decision = RoutingDecision(
        intents=[
            IntentDecision(
                intent=Intent.ORDER,
                confidence=0.8,
                requires_knowledge=False,
                requires_tools=True,
            ),
            IntentDecision(
                intent=Intent.REFUND,
                confidence=0.75,
                requires_knowledge=True,
                requires_tools=True,
            ),
        ],
        requires_context=False,
        should_clarify=False,
        reason_code="multi_intent",
    )
    assert len(decision.intents) == 2


@pytest.mark.anyio
async def test_resolve_customer_routing_uses_deterministic_when_llm_disabled(monkeypatch):
    reset_aggregate_for_tests()
    monkeypatch.setattr(settings, "ai_intent_router_enabled", False)
    resolution = await resolve_customer_routing("hey whats up", [], channel="widget")
    assert resolution.mode == "deterministic"
    assert resolution.llm is None


@pytest.mark.anyio
async def test_llm_router_failure_falls_back_without_crashing(monkeypatch):
    reset_aggregate_for_tests()
    monkeypatch.setattr(settings, "ai_intent_router_enabled", True)
    monkeypatch.setattr(
        "app.features.ai.application.intent_routing.llm_router.is_provider_configured",
        lambda: True,
    )

    async def fail(*_args, **_kwargs):
        from app.features.ai.infrastructure.llm_gateway import AIProviderError

        raise AIProviderError("provider_timeout", "timeout")

    monkeypatch.setattr(
        "app.features.ai.application.intent_routing.llm_router.generate_completion",
        fail,
    )
    resolution = await resolve_customer_routing(
        "My order is late and I want a refund.", [], channel="widget"
    )
    assert resolution.mode == "deterministic_fallback"
    assert resolution.failure_code == "provider_timeout"
    plan = apply_routing_to_widget_plan(
        "My order is late and I want a refund.", [], resolution
    )
    assert plan.route in {"sensitive", "knowledge", "clarification"}


def test_competing_multi_intent_routes_sensitive_when_possible():
    assessment = assess_deterministic_route("My order is late and I want a refund.", [])
    from app.features.ai.application.intent_routing.service import CustomerRoutingResolution

    resolution = CustomerRoutingResolution(deterministic=assessment, multi_intent=True)
    plan = apply_routing_to_widget_plan("My order is late and I want a refund.", [], resolution)
    assert plan.route == "sensitive"


def test_duplicate_llm_intents_rejected():
    with pytest.raises(ValidationError):
        RoutingDecision(
            intents=[
                IntentDecision(intent=Intent.PRODUCT, confidence=0.8, requires_knowledge=True, requires_tools=False),
                IntentDecision(intent=Intent.PRODUCT, confidence=0.7, requires_knowledge=True, requires_tools=False),
            ],
            reason_code="duplicate",
        )


@pytest.mark.anyio
async def test_llm_cannot_upgrade_non_tool_route_to_commerce(monkeypatch):
    from app.features.ai.application.intent_routing import service

    monkeypatch.setattr(settings, "ai_intent_router_enabled", True)
    async def fake_router(*_args, **_kwargs):
        return RoutingDecision(
            intents=[IntentDecision(intent=Intent.ORDER, confidence=0.99, requires_knowledge=False, requires_tools=True)],
            reason_code="unsafe_upgrade",
        ), {}, "fake-model", None
    monkeypatch.setattr(service, "invoke_llm_intent_router", fake_router)
    result = await resolve_customer_routing("What is your shipping policy?", [], channel="widget")
    assert result.llm is None
    assert result.mode == "deterministic_fallback"
    assert result.failure_code == "unsafe_llm_commerce_escalation"


@pytest.mark.anyio
async def test_low_confidence_llm_intent_requests_clarification(monkeypatch):
    from app.features.ai.application.intent_routing import service

    monkeypatch.setattr(settings, "ai_intent_router_enabled", True)
    async def fake_router(*_args, **_kwargs):
        return RoutingDecision(
            intents=[IntentDecision(intent=Intent.KNOWLEDGE, confidence=0.3, requires_knowledge=True, requires_tools=False)],
            reason_code="uncertain",
        ), {}, "fake-model", None
    monkeypatch.setattr(service, "invoke_llm_intent_router", fake_router)
    result = await resolve_customer_routing("What is your shipping policy?", [], channel="widget")
    assert result.clarify is True
    plan = apply_routing_to_widget_plan("What is your shipping policy?", [], result)
    assert plan.route == "clarification"


@pytest.mark.anyio
async def test_fallback_preserves_multi_intent_flag(monkeypatch):
    from app.features.ai.application.intent_routing import service

    monkeypatch.setattr(settings, "ai_intent_router_enabled", True)

    async def failing_router(*_args, **_kwargs):
        return None, {}, None, "provider_timeout"

    monkeypatch.setattr(service, "invoke_llm_intent_router", failing_router)
    result = await resolve_customer_routing(
        "My order is late and I want a refund.", [], channel="widget"
    )
    assert result.mode == "deterministic_fallback"
    assert result.multi_intent is True
    assert result.failure_code == "provider_timeout"


def test_knowledge_question_does_not_gain_sensitive_route_from_llm():
    from app.features.ai.application.intent_routing.service import CustomerRoutingResolution

    assessment = assess_deterministic_route("What is your shipping policy?", [])
    decision = RoutingDecision(
        intents=[IntentDecision(intent=Intent.ORDER, confidence=0.99, requires_knowledge=False, requires_tools=True)],
        reason_code="unsafe_upgrade",
    )
    result = CustomerRoutingResolution(deterministic=assessment, llm=decision)
    plan = apply_routing_to_widget_plan("What is your shipping policy?", [], result)
    assert plan.route != "sensitive"


def test_intent_router_cost_requires_exact_model_pricing(monkeypatch):
    from app.features.ai.application.intent_routing.metrics import estimate_router_cost_usd

    monkeypatch.setattr(settings, "ai_model_prices", {
        "router-model": {"input": 0.20, "output": 0.80},
    })
    monkeypatch.setattr(settings, "ai_model", "generation-model")
    assert estimate_router_cost_usd(
        prompt_tokens=1000, completion_tokens=500, model_name="router-model",
    ) == pytest.approx(0.0006)
    assert estimate_router_cost_usd(
        prompt_tokens=1000, completion_tokens=500, model_name="unknown",
    ) is None


def test_structured_router_separates_message_act_from_knowledge_topic():
    from app.features.ai.application.intent_routing.service import CustomerRoutingResolution

    assessment = assess_deterministic_route("I did not demand any refund", [])
    statement = RoutingDecision.model_validate({
        "intents": [{
            "intent": "knowledge", "confidence": 0.92,
            "requires_knowledge": True, "requires_tools": False,
        }],
        "reason_code": "policy_subject",
        "customer_message_act": "statement",
    })
    outcome = CustomerRoutingResolution(
        deterministic=assessment, llm=statement,
    ).tool_outcome()
    assert outcome["customer_message_act"] == "statement"
    assert outcome["primary_intent"] == assessment.intent.value


def test_structured_router_accepts_direct_and_indirect_requests():
    for content in ("Do you deliver to Pokhara?", "I need your refund policy"):
        assessment = assess_deterministic_route(content, [])
        decision = RoutingDecision.model_validate({
            "intents": [{
                "intent": "knowledge", "confidence": 0.92,
                "requires_knowledge": True, "requires_tools": False,
            }],
            "reason_code": "information_request",
            "customer_message_act": "information_request",
        })
        from app.features.ai.application.intent_routing.service import CustomerRoutingResolution
        assert CustomerRoutingResolution(
            deterministic=assessment, llm=decision,
        ).tool_outcome()["customer_message_act"] == "information_request"


def test_missing_or_invalid_message_act_fails_closed():
    from app.features.ai.application.intent_routing.service import CustomerRoutingResolution

    assessment = assess_deterministic_route("I did not demand any refund", [])
    old_model_response = RoutingDecision.model_validate({
        "intents": [{
            "intent": "knowledge", "confidence": 0.8,
            "requires_knowledge": True, "requires_tools": False,
        }],
        "reason_code": "legacy",
    })
    assert CustomerRoutingResolution(
        deterministic=assessment, llm=old_model_response,
    ).tool_outcome()["customer_message_act"] == "unclear"
    with pytest.raises(ValidationError):
        RoutingDecision.model_validate({
            "intents": [{
                "intent": "knowledge", "confidence": 0.8,
                "requires_knowledge": True, "requires_tools": False,
            }],
            "reason_code": "invalid",
            "customer_message_act": "always_create_gap",
        })
