from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

AllowedAIAgentTool = Literal["recommend_products", "compare_products"]


class AIAgentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    system_instructions: str = Field(default="", max_length=8000)
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=50)
    allowed_tools: list[AllowedAIAgentTool] = Field(
        default_factory=lambda: ["recommend_products", "compare_products"], max_length=2
    )

    @field_validator("allowed_tools")
    @classmethod
    def unique_tools(cls, value: list[AllowedAIAgentTool]) -> list[AllowedAIAgentTool]:
        if len(set(value)) != len(value):
            raise ValueError("AI tools may only be enabled once")
        return value

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class AIAgentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    system_instructions: str = Field(default="", max_length=8000)
    knowledge_base_ids: list[UUID] | None = Field(default=None, max_length=50)
    allowed_tools: list[AllowedAIAgentTool] | None = Field(default=None, max_length=2)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("allowed_tools")
    @classmethod
    def unique_tools(cls, value: list[AllowedAIAgentTool] | None) -> list[AllowedAIAgentTool] | None:
        if value is not None and len(set(value)) != len(value):
            raise ValueError("AI tools may only be enabled once")
        return value


class AIAgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    system_instructions: str
    status: str
    config_version: int
    is_default: bool
    allowed_tools: list[AllowedAIAgentTool] = Field(default_factory=list)
    knowledge_base_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class AIAgentPage(BaseModel):
    items: list[AIAgentOut]
    total: int
    limit: int
    offset: int


class AIAgentAuditOut(BaseModel):
    id: UUID
    ai_agent_id: UUID
    actor_user_id: UUID
    actor_name: str
    event_type: str
    config_version: int
    details: dict[str, object]
    created_at: datetime


class AIAgentAuditPage(BaseModel):
    items: list[AIAgentAuditOut]
    total: int
    limit: int
    offset: int


class AIAgentKnowledgeBasesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    knowledge_base_ids: list[UUID] = Field(max_length=50)
