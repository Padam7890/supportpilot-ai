"""Validated structured contracts for optional LLM intent routing."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Intent(str, Enum):
    GREETING = "greeting"
    GENERAL = "general"
    KNOWLEDGE = "knowledge"
    PRODUCT = "product"
    ORDER = "order"
    REFUND = "refund"
    COMPLAINT = "complaint"
    CLARIFICATION = "clarification"
    HANDOFF = "handoff"


class IntentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    confidence: float = Field(ge=0, le=1)
    requires_knowledge: bool
    requires_tools: bool


class RoutingDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intents: list[IntentDecision] = Field(min_length=1, max_length=4)
    requires_context: bool = False
    should_clarify: bool = False
    reason_code: str = Field(min_length=1, max_length=64)

    @field_validator("reason_code")
    @classmethod
    def reason_is_safe(cls, value: str) -> str:
        cleaned = value.strip().replace("\n", " ")
        if not cleaned or len(cleaned) > 64:
            raise ValueError("reason_code is invalid")
        return cleaned


class DeterministicRouteAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    confidence: float = Field(ge=0, le=1)
    candidate_intents: list[Intent] = Field(max_length=8)
    requires_context: bool
    requires_tools: bool
    requires_knowledge: bool
    risk_level: str = Field(pattern=r"^(low|medium|high)$")
    competing: bool
    reason_code: str
