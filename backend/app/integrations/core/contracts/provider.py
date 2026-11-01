from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.core.types import IntegrationCapability


class ProviderDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_]{1,47}$")
    display_name: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=40)
    capabilities: frozenset[IntegrationCapability]


class IntegrationConnectionRef(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    organization_id: UUID
    provider_id: str
    external_account_id: str = Field(min_length=1, max_length=512)
