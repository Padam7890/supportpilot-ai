"""Typed, read-only tool selection contracts for the conversation agent.

This module plans tool requests. It never executes provider operations or
authorizes private customer data access.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ToolName(str, Enum):
    KNOWLEDGE_SEARCH = "knowledge_search"
    CATALOG_SEARCH = "catalog_search"
    ORDER_LOOKUP = "order_lookup"
    SUPPORT_HANDOFF = "support_handoff"


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ToolName
    query: str = Field(min_length=1, max_length=1200)
    verified_customer_id: str | None = Field(default=None, max_length=128)
    order_reference: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_private_lookup(self) -> "ToolRequest":
        if self.name == ToolName.ORDER_LOOKUP and not (
            self.verified_customer_id and self.order_reference
        ):
            raise ValueError("Order lookup requires verified identity and order reference")
        if self.name != ToolName.ORDER_LOOKUP and (
            self.verified_customer_id is not None or self.order_reference is not None
        ):
            raise ValueError("Identity and order fields are restricted to order lookup")
        return self


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: ToolName
    status: str = Field(pattern=r"^(ok|not_found|denied|unavailable)$")
    facts: list[str] = Field(default_factory=list, max_length=20)
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    error_code: str | None = Field(default=None, max_length=64)
