"""Validated conversation agent boundaries, separate from provider implementation."""

from pydantic import BaseModel, ConfigDict, Field

from app.features.ai.application.conversation_tool_contracts import ToolRequest


class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sender: str = Field(pattern=r"^(customer|assistant)$")
    content: str = Field(min_length=1, max_length=1200)


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str = Field(min_length=1, max_length=1200)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=12)
    channel: str = Field(pattern=r"^(widget|playground|whatsapp|messenger)$")


class AgentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    response_mode: str = Field(pattern=r"^(answer|tool|clarify|handoff)$")
    tool_requests: list[ToolRequest] = Field(default_factory=list, max_length=3)
    clarification: str | None = Field(default=None, max_length=500)
    reasoning_code: str = Field(min_length=1, max_length=64)
