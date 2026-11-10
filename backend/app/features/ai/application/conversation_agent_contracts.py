"""Validated conversation agent boundaries, separate from provider implementation."""

from pydantic import BaseModel, ConfigDict, Field

class ConversationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sender: str = Field(pattern=r"^(customer|assistant)$")
    content: str = Field(min_length=1, max_length=1200)


class AgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    message: str = Field(min_length=1, max_length=1200)
    history: list[ConversationTurn] = Field(default_factory=list, max_length=12)
    channel: str = Field(pattern=r"^(widget|widget_reply|playground|reply_draft)$")
