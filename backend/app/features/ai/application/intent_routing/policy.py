"""When to invoke the optional structured LLM router."""

from app.core.config import settings
from app.features.ai.application.conversational_intents import classify_conversational_intent
from app.features.ai.application.intent_routing.schemas import DeterministicRouteAssessment, Intent


def should_invoke_llm_router(assessment: DeterministicRouteAssessment, message: str) -> bool:
    if not settings.ai_intent_router_enabled:
        return False
    if assessment.intent == Intent.HANDOFF and assessment.confidence >= 0.9:
        return False
    if classify_conversational_intent(message) is not None and not assessment.competing:
        return False
    high = settings.ai_intent_router_high_confidence
    low = settings.ai_intent_router_low_confidence
    if assessment.confidence >= high and not assessment.competing:
        return False
    if assessment.competing:
        return True
    if assessment.confidence < low:
        return True
    if assessment.requires_context and assessment.confidence < high:
        return True
    return low <= assessment.confidence < high
